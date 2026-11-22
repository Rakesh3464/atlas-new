#!/usr/bin/env python3
"""Adapt SUSFS 4.19 mount hunks to Samsung A21s' fs_context based VFS.

Run only in a throwaway CI checkout. Every edit must match exactly once;
otherwise exit nonzero. A successful patch is NOT proof of boot compatibility.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

SKIP = {
    "fs/namespace.c": {1, 7, 8, 9, 10},
    "fs/stat.c": {3},
    "include/linux/mount.h": {1},
    "kernel/sys.c": {1},
}


def without_incompatible_hunks(patch_text):
    sections = re.split(r"(?=^diff --git a/)", patch_text, flags=re.M)
    output = [sections[0]]
    removed = {}
    for section in sections[1:]:
        header = re.match(r"diff --git a/(\S+) b/", section)
        if not header:
            output.append(section)
            continue
        path = header.group(1)
        hunks = list(re.finditer(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@[^\n]*\n", section, re.M))
        if not hunks:
            output.append(section)
            continue
        kept = []
        for n, hunk in enumerate(hunks, 1):
            end = hunks[n].start() if n < len(hunks) else len(section)
            if n in SKIP.get(path, set()):
                removed.setdefault(path, set()).add(n)
            else:
                kept.append(section[hunk.start():end])
        if kept:
            output.append(section[:hunks[0].start()] + "".join(kept))
    if removed != SKIP:
        raise RuntimeError("Unexpected upstream SUSFS patch revision/hunks: " + repr(removed))
    return "".join(output)


def replace_once(file, old, new):
    path = pathlib.Path(file)
    content = path.read_text()
    if content.count(old) != 1:
        raise RuntimeError(f"Expected exactly one source anchor in {file}; found {content.count(old)}: {old[:70]!r}")
    path.write_text(content.replace(old, new, 1))


def patch_with_context(patch_text):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch") as f:
        f.write(patch_text)
        f.flush()
        subprocess.run(["patch", "-p1", "--batch", "--forward", "--dry-run", "-i", f.name], check=True)
        subprocess.run(["patch", "-p1", "--batch", "--forward", "-i", f.name], check=True)


def port_namespace():
    replace_once("fs/namespace.c",
        '#include <linux/fs_context.h>\n\n#include "pnode.h"',
        '''#include <linux/fs_context.h>
#if defined(CONFIG_KSU_SUSFS_SUS_MOUNT) || defined(CONFIG_KSU_SUSFS_TRY_UMOUNT)
#include <linux/susfs_def.h>
#endif

#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
extern bool susfs_is_current_ksu_domain(void);
extern bool susfs_is_current_zygote_domain(void);
static DEFINE_IDA(susfs_mnt_id_ida);
static DEFINE_IDA(susfs_mnt_group_ida);
#define CL_COPY_MNT_NS BIT(25)
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
extern void susfs_auto_add_sus_ksu_default_mount(const char __user *to_pathname);
bool susfs_is_auto_add_sus_ksu_default_mount_enabled = true;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
extern int susfs_auto_add_sus_bind_mount(const char *pathname, struct path *path_target);
bool susfs_is_auto_add_sus_bind_mount_enabled = true;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
extern void susfs_auto_add_try_umount_for_bind_mount(struct path *path);
bool susfs_is_auto_add_try_umount_for_bind_mount_enabled = true;
#endif

#include "pnode.h"''')

    replace_once("fs/namespace.c",
        "struct vfsmount *vfs_create_mount(struct fs_context *fc)\n{\n\tstruct mount *mnt;\n",
        """struct vfsmount *vfs_create_mount(struct fs_context *fc)
{
\tstruct mount *mnt;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tstruct mount *m;
\tstruct mnt_namespace *mnt_ns;
\tint mnt_id;
#endif
""")
    replace_once("fs/namespace.c",
        '\tmnt = alloc_vfsmnt(fc->source ?: "none");',
        '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tmnt = alloc_vfsmnt(fc->source ?: "none",
\t\t\tsusfs_is_current_ksu_domain(), 0);
#else
\tmnt = alloc_vfsmnt(fc->source ?: "none");
#endif''')
    replace_once("fs/namespace.c",
        "\tmnt->mnt_parent\t\t= mnt;\n\n\tlock_mount_hash();",
        '''\tmnt->mnt_parent\t\t= mnt;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\t/* SUSFS mount-ID handling for fs_context's vfs_create_mount(). */
\tif (susfs_is_current_zygote_domain() && current->nsproxy) {
\t\tmnt_ns = current->nsproxy->mnt_ns;
\t\tif (mnt_ns && !list_empty(&mnt_ns->list)) {
\t\t\tget_mnt_ns(mnt_ns);
\t\t\trcu_read_lock();
\t\t\tmnt_id = list_first_entry(&mnt_ns->list,
\t\t\t\t\tstruct mount, mnt_list)->mnt_id;
\t\t\tlist_for_each_entry_rcu(m, &mnt_ns->list, mnt_list) {
\t\t\t\tif (m->mnt_id < DEFAULT_SUS_MNT_ID)
\t\t\t\t\tmnt_id++;
\t\t\t}
\t\t\tWRITE_ONCE(mnt->mnt.susfs_mnt_id_backup,
\t\t\t\t\tREAD_ONCE(mnt->mnt_id));
\t\t\tWRITE_ONCE(mnt->mnt_id, READ_ONCE(mnt_id));
\t\t\trcu_read_unlock();
\t\t\tput_mnt_ns(mnt_ns);
\t\t}
\t}
#endif

\tlock_mount_hash();''')

    replace_once("fs/namespace.c",
        "\tstruct super_block *sb = old->mnt.mnt_sb;\n\tstruct mount *mnt;\n\tint err;\n\n\tmnt = alloc_vfsmnt(old->mnt_devname);",
        '''\tstruct super_block *sb = old->mnt.mnt_sb;
\tstruct mount *mnt;
\tint err;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tstruct mount *m;
\tstruct mnt_namespace *mnt_ns;
\tint mnt_id;
\tbool is_current_ksu_domain = susfs_is_current_ksu_domain();
\tbool is_current_zygote_domain = susfs_is_current_zygote_domain();
\tif (unlikely(is_current_ksu_domain)) {
\t\tif (!(flag & CL_COPY_MNT_NS)) {
\t\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, 0);
\t\t} else {
\t\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, old->mnt_id);
\t\t\tif (mnt)
\t\t\t\tmnt->mnt.susfs_mnt_id_backup =
\t\t\t\t\tDEFAULT_SUS_MNT_ID_FOR_KSU_PROC_UNSHARE;
\t\t}
\t} else if (old->mnt_id >= DEFAULT_SUS_MNT_ID) {
\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, 0);
\t} else {
\t\tmnt = alloc_vfsmnt(old->mnt_devname, false, 0);
\t}
#else
\tmnt = alloc_vfsmnt(old->mnt_devname);
#endif''')
    replace_once("fs/namespace.c",
        "\tmnt->mnt_parent = mnt;\n\tlock_mount_hash();\n\tlist_add_tail(&mnt->mnt_instance, &sb->s_mounts);",
        '''\tmnt->mnt_parent = mnt;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tif (is_current_zygote_domain && !(flag & CL_COPY_MNT_NS)
\t\t\t&& current->nsproxy) {
\t\tmnt_ns = current->nsproxy->mnt_ns;
\t\tif (mnt_ns && !list_empty(&mnt_ns->list)) {
\t\t\tget_mnt_ns(mnt_ns);
\t\t\trcu_read_lock();
\t\t\tmnt_id = list_first_entry(&mnt_ns->list,
\t\t\t\t\tstruct mount, mnt_list)->mnt_id;
\t\t\tlist_for_each_entry_rcu(m, &mnt_ns->list, mnt_list) {
\t\t\t\tif (m->mnt_id < DEFAULT_SUS_MNT_ID)
\t\t\t\t\tmnt_id++;
\t\t\t}
\t\t\tWRITE_ONCE(mnt->mnt.susfs_mnt_id_backup,
\t\t\t\t\tREAD_ONCE(mnt->mnt_id));
\t\t\tWRITE_ONCE(mnt->mnt_id, READ_ONCE(mnt_id));
\t\t\trcu_read_unlock();
\t\t\tput_mnt_ns(mnt_ns);
\t\t}
\t}
#endif
\tlock_mount_hash();
\tlist_add_tail(&mnt->mnt_instance, &sb->s_mounts);''')


def port_stat():
    replace_once("fs/stat.c",
        "\tunsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;\n\n#ifdef CONFIG_KSU\n",
        '''\tunsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tstruct mount *mnt;
#endif

#ifdef CONFIG_KSU
''')
    # The upstream hunk otherwise leaks a path reference under SUS_MOUNT.
    replace_once("fs/stat.c",
        "\tstat->mnt_id = mnt->mnt_id;\n#else\n\tpath_put(&path);\n#endif\n",
        "\tstat->mnt_id = mnt->mnt_id;\n#endif\n\tpath_put(&path);\n")


def port_mount_header():
    replace_once("include/linux/mount.h",
        "\tANDROID_KABI_RESERVE(4);\n",
        '''#ifdef CONFIG_KSU_SUSFS
\tANDROID_KABI_USE(4, u64 susfs_mnt_id_backup);
#else
\tANDROID_KABI_RESERVE(4);
#endif
''')


def port_uname():
    replace_once("kernel/sys.c",
        "SYSCALL_DEFINE1(newuname, struct new_utsname __user *, name)\n",
        '''#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
extern void susfs_spoof_uname(struct new_utsname *tmp);
#endif
SYSCALL_DEFINE1(newuname, struct new_utsname __user *, name)
''')
    replace_once("kernel/sys.c",
        "\tdown_read(&uts_sem);\n\tmemcpy(&tmp, utsname(), sizeof(tmp));\n#ifndef CONFIG_FAKE_UNAME_NONE\n",
        '''\tdown_read(&uts_sem);
\tmemcpy(&tmp, utsname(), sizeof(tmp));
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
\tsusfs_spoof_uname(&tmp);
#endif
#ifndef CONFIG_FAKE_UNAME_NONE
''')


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: a21s-port-susfs.py KERNEL_PATCH")
    patch_text = pathlib.Path(sys.argv[1]).read_text()
    patch_with_context(without_incompatible_hunks(patch_text))
    port_namespace()
    port_stat()
    port_mount_header()
    port_uname()
    print("A21s fs_context-specific SUSFS mount patch adapted; still requires compile and device validation")


if __name__ == "__main__":
    main()
