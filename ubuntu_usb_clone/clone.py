#! /usr/bin/env python3

import sys
import subprocess
import time

VERSION = "1.1"
IMAGE_VERSION = "Ubuntu 22.04.2 LTS"


archives = ["uefi.bz2", "filesystem.bz2", "clone.py"]

def yes_or_no(question):
    while "the answer is invalid":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[:1] == 'y':
            return True
        if reply[:1] == 'n':
            return False

def issue_command(command):
    cp = subprocess.run(command,
                        universal_newlines=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)

    if cp.returncode != 0:
        return (False, cp.stderr)
    else: 
        return (True, cp.stdout)

def get_image_uuids(fstab):
    efi_uuid = ""
    fs_uuid = ""
    with open(fstab, "r") as fstab_in:
        lines = fstab_in.readlines()
        for line in lines:
            if (line.find("UUID=") == 0):
                items = line.split()
                if items[1] == "/":
                    fs_uuid = items[0].split("=")[1]
                if items[1] == "/boot/efi":
                    efi_uuid = items[0].split("=")[1]
    return [efi_uuid, fs_uuid]

def get_removable_type(drive):
    removable = False

    sysfs_path = "/sys/block/{}/removable".format(drive)

    with open(sysfs_path, 'r') as sys_in:
        removable_type = sys_in.readline().strip() 
        if removable_type == '1':
            removable = True
    return removable


def get_partion_info(drive_dev_path):
    disk_info = []
    (ret, msg) = issue_command(["parted", "-s", drive_dev_path, "print"])

    if not ret:
        print(msg)
        return disk_info

    disk_info.append(msg)

    lines = msg.split('\n')
    partition_info_lines = False


    for line in lines:
        if "Number" in line:
            partition_info_lines = True
            continue
        if partition_info_lines:
            part_info = line.split()
            if len(part_info) > 0:
                disk_info.append(part_info[0])
    return disk_info

def unmount_partitions(drive_dev_path, partitions):
    proc_mount = "/proc/mounts"
    drive_parts = [ "{}{}".format(drive_dev_path, x) for x in partitions ] 
    mounted_partitions = []
    with open(proc_mount, 'r') as mount_in:
        mounts = mount_in.readlines()
        for mount in mounts:
            for drive_part in drive_parts:
                if drive_part in mount:
                    mounted_partitions.append(drive_part)
    for mount in mounted_partitions:
        print("unmounting {}\n".format(mount))
        (ret, msg) = issue_command(["umount", mount])

        if not ret:
            print(msg)
            return False
        else: 
            print(msg)
    return True

def delete_partitions(drive_dev_path, partitions):
    partitions.reverse()

    del_cmd = ["parted", "-s", drive_dev_path]
    for p in partitions:
        del_cmd.append("rm")
        del_cmd.append(p)

    print("Deleting partitions")
    print(" ".join(del_cmd))

    (ret, msg) = issue_command(del_cmd)

    if not ret:
        print(msg)
        return False
    else: 
        print(msg)
        return True

def prepare_partitions(drive_dev_path):
    print("creating partitions")
    part_cmd = ["parted", "-s", drive_dev_path]

    (ret, msg) = issue_command(part_cmd + ["mklabel", "gpt"])
    if not ret:
        print(msg)
        return False

    (ret, msg) = issue_command(part_cmd + ["mkpart", "primary", "fat32", "1MiB", "101MiB"])
    if not ret:
        print(msg)
        return False

    (ret, msg) = issue_command(part_cmd + ["set", "1", "esp", "on", "set", "1", "boot", "on"])
    if not ret:
        print(msg)
        return False

    (ret, msg) = issue_command(part_cmd + ["mkpart", "primary", "ext4", "101MiB", "100%"])
    if not ret:
        print(msg)
        return False

    (ret, msg) = issue_command(["partprobe", "-s", drive_dev_path])
    if not ret:
        print(msg)
        return False
    print(msg)

    return True

def format_partitions(drive_dev_path):
    print("formatting partitions...")

    (ret, msg) = issue_command(["mkfs.fat", drive_dev_path + "1"])
    if not ret:
        print(msg)
        return False
    print(msg)

    (ret, msg) = issue_command(["mkfs.ext4", "-F", drive_dev_path + "2"])
    if not ret:
        print(msg)
        return False
    print(msg)

def get_uuids(drive_dev_path):
    uuids = []
    partitions = [drive_dev_path + "1", drive_dev_path + "2"]
    for p in partitions:
        (ret, msg) = issue_command(["blkid", p])
        if not ret:
            print(msg)
            return False
        items = msg.split()
        for i in items:
            if i.find("UUID=") == 0:
                uuids.append(i.split('"')[1])
    return uuids


def copy_filesystem(drive_dev_path, uuids):
    print("copying file system(may take 30 min)...")

    if len(uuids) != 2:
        print("Invalid partitions uuid count, {}\n".format(len(uuids)))
        return False

    for i in range(len(uuids)):
        dst_path = "/tmp/{}".format(uuids[i])
        (ret, msg) = issue_command(["mkdir", "-p", dst_path])
        if not ret:
            print(msg)
            return False

        (ret, msg) = issue_command(["mount", drive_dev_path + str(i+1), dst_path])
        if not ret:
            print(msg)
            return False

        (ret, msg) = issue_command(["tar", "xjf", archives[i], "-C", dst_path])
        if not ret:
            print(msg)
            return False

        if i == 0:
            (ret, msg) = issue_command(["sed", "-i", "s/search.fs_uuid [^[:space:]]\+/search.fs_uuid {}/g".format(uuids[1]), dst_path + "/EFI/ubuntu/grub.cfg"])
            if not ret:
                print(msg)
                return False
        else:
            archive_uuid = get_image_uuids(dst_path + "/etc/fstab")

            (ret, msg) = issue_command(["sed", "-i", "s/{}/{}/g".format(archive_uuid[0], uuids[0]), dst_path + "/etc/fstab"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["sed", "-i", "s/{}/{}/g".format(archive_uuid[1], uuids[1]), dst_path + "/etc/fstab"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["chmod", "+w", dst_path + "/boot/grub/grub.cfg"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["sed", "-i", "s/{}/{}/g".format(archive_uuid[1], uuids[1]), dst_path + "/boot/grub/grub.cfg"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["chmod", "-w", dst_path + "/boot/grub/grub.cfg"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["mkdir", dst_path + "/home/programmer/clone"])
            if not ret:
                print(msg)
                return False

            (ret, msg) = issue_command(["cp"] + archives + [dst_path + "/home/programmer/clone/"])
            if not ret:
                print(msg)
                return False

        (ret, msg) = issue_command(["umount", dst_path])
        if not ret:
            print(msg)
            return False



if __name__ == "__main__":
    print("{} VERSION {}\n".format(sys.argv[0], VERSION))
    start = time.time()

    if len(sys.argv) != 2:
        print("Argument error\nUsage: {} <install_drive>\n".format(sys.argv[0]))
        exit(1)

    drive = sys.argv[1]
    drive_dev_path = "/dev/{}".format(drive)

#    if not get_removable_type(drive): 
#        print("{} is not a removable drive".format(drive_dev_path))
#        exit(1)

    drive_info = get_partion_info(drive_dev_path)

    if len(drive_info) > 0:
        print('{} will be cloned to the following drive'.format(IMAGE_VERSION))
        print(drive_info[0])
        if not yes_or_no("Continue writing into above drive"):
            exit(1)

    # if it has already contain partitions 
    if len(drive_info) > 1:
        unmount_partitions(drive_dev_path, drive_info[1:])
        delete_partitions(drive_dev_path, drive_info[1:])

    if not prepare_partitions(drive_dev_path):
        exit(1)

    time.sleep(1)

    format_partitions(drive_dev_path)
    uuids = get_uuids(drive_dev_path)
    print(uuids)

    ret = copy_filesystem(drive_dev_path, uuids)
    elapsed = time.time() - start
    print("cloned in {}\n".format(time.strftime("%H:%M:%S", time.gmtime(elapsed))))
