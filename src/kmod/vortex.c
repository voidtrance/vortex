// SPDX-License-Identifier: GPL-2.0+
/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2025 Mitko Haralanov
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
#include <linux/init.h>
#include <linux/module.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/uaccess.h>
#include <linux/fs.h>
#include <linux/mm.h>
#include <linux/ktime.h>
#include <linux/delay.h>
#include "vortex.h"

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Mitko Haralanov <voidtrance@gmail.com>");
MODULE_DESCRIPTION("Vortex Emulator time control module");

static int vortex_open(struct inode *inode, struct file *file);
static int vortex_release(struct inode *inode, struct file *file);
static int vortex_mmap(struct file *file, struct vm_area_struct *vma);
static vm_fault_t vortex_mmap_fault(struct vm_fault *fault);
static ssize_t vortex_read(struct file *file, char __user *buf, size_t count,
                           loff_t *offset);
static long vortex_ioctl(struct file *file, unsigned int cmd,
                         unsigned long arg);

static const struct file_operations vortex_fops = { .owner = THIS_MODULE,
                                                    .open = vortex_open,
                                                    .release = vortex_release,
                                                    .read = vortex_read,
                                                    .unlocked_ioctl =
                                                        vortex_ioctl,
                                                    .mmap = vortex_mmap };

static const struct vm_operations_struct vortex_vm_ops = {
    .fault = vortex_mmap_fault,
};

struct vortex_device_data {
    struct class *class;
    struct device *device;
    struct cdev cdev;
    unsigned int dev_num;
    int dev_major;
};

struct vortex_ctxt {
    struct vortex_cmd_init config;
    struct vortex_time_data *data;
    ktime_t start_time;
    ktime_t pause_start;
    uint64_t time_offset;
    bool pause;
};

static struct vortex_device_data vortex_device;

static int vortex_uevent(const struct device *dev,
                         struct kobj_uevent_env *env) {
    add_uevent_var(env, "DEVMODE=%#o", 0666);
    return 0;
}

static int __init vortex_init(void) {
    int ret;
    dev_t dev;

    ret = alloc_chrdev_region(&dev, 0, 1, "vortex");
    if (ret)
        return ret;

    vortex_device.dev_major = MAJOR(dev);
    vortex_device.dev_num = MKDEV(vortex_device.dev_major, 0);
    vortex_device.class = class_create("vortex");
    if (IS_ERR_VALUE(vortex_device.class)) {
        unregister_chrdev_region(vortex_device.dev_num, MINORMASK);
        return PTR_ERR(vortex_device.class);
    }

    vortex_device.class->dev_uevent = vortex_uevent;

    cdev_init(&vortex_device.cdev, &vortex_fops);
    vortex_device.cdev.owner = THIS_MODULE;
    ret = cdev_add(&vortex_device.cdev, vortex_device.dev_num, 1);
    if (ret) {
        class_unregister(vortex_device.class);
        class_destroy(vortex_device.class);
        unregister_chrdev_region(vortex_device.dev_num, MINORMASK);
        return ret;
    }

    vortex_device.device = device_create(vortex_device.class, NULL,
                                         vortex_device.dev_num, NULL, "vortex");
    if (IS_ERR_VALUE(vortex_device.device)) {
        class_unregister(vortex_device.class);
        class_destroy(vortex_device.class);
        unregister_chrdev_region(vortex_device.dev_num, MINORMASK);
        return PTR_ERR(vortex_device.device);
    }

    return 0;
}

static void __exit vortex_exit(void) {
    device_destroy(vortex_device.class, vortex_device.dev_num);
    class_unregister(vortex_device.class);
    class_destroy(vortex_device.class);
    unregister_chrdev_region(vortex_device.dev_num, MINORMASK);
}

static int vortex_open(struct inode *inode, struct file *file) {
    struct vortex_ctxt *ctxt;

    ctxt = kmalloc(sizeof(*ctxt), GFP_KERNEL);
    if (!ctxt)
        return -ENOMEM;

    memset(ctxt, 0, sizeof(ctxt));
    ctxt->data = (struct vortex_time_data *)get_zeroed_page(GFP_KERNEL);
    file->private_data = ctxt;
    return 0;
}

static int vortex_release(struct inode *inode, struct file *file) {
    struct vortex_ctxt *ctxt = file->private_data;

    file->private_data = NULL;
    free_page((unsigned long)ctxt->data);
    kfree(ctxt);
    return 0;
}

static ssize_t vortex_read(struct file *file, char __user *buf, size_t count,
                           loff_t *offset) {
    struct vortex_ctxt *ctxt = file->private_data;

    if (ctxt->config.sleep_ns == 0 || ctxt->config.tick_time == 0)
        return -EIO;

    if (count > sizeof(struct vortex_time_data))
        return -EINVAL;

    if (likely(ctxt->config.sleep_ns)) {
        if (ctxt->config.sleep_ns >= 1000)
            usleep_range_idle(ctxt->config.sleep_ns / 1000,
                              ctxt->config.sleep_ns / 1000);
        else
            ndelay(ctxt->config.sleep_ns);
    }

    if (!ctxt->pause) {
        ctxt->data->runtime =
            ktime_to_ns(ktime_sub(ktime_get_raw(), ctxt->start_time)) -
            ctxt->time_offset;
        ctxt->data->ticks =
            (u64)((ctxt->data->runtime / ctxt->config.tick_time) &
                  ((1UL << ctxt->config.width) - 1));
    }

    if (copy_to_user(buf, ctxt->data, count))
        return -EFAULT;

    return count;
}

static long vortex_ioctl(struct file *file, unsigned int cmd,
                         unsigned long arg) {
    struct vortex_ctxt *ctxt = file->private_data;

    switch (cmd) {
    case VORTEX_CMD_INIT:
        if (ctxt->config.sleep_ns)
            return -EINVAL;

        if (_IOC_SIZE(cmd) != sizeof(struct vortex_cmd_init))
            return -EINVAL;

        if (copy_from_user(&ctxt->config, (void __user *)arg,
                           sizeof(struct vortex_cmd_init)))
            return -EFAULT;

        /*
         * Ideally, we can just fall through to VORTEX_CMD_RESET
         * but the compiler complains.
         */
        ctxt->start_time = ktime_get_raw();
        break;
    case VORTEX_CMD_RESET:
        ctxt->start_time = ktime_get_raw();
        ctxt->time_offset = 0;
        break;
    case VORTEX_CMD_PAUSE:
        ctxt->pause = true;
        ctxt->pause_start = ktime_get_raw();
        break;
    case VORTEX_CMD_RESUME:
        ctxt->time_offset +=
            ktime_to_ns(ktime_sub(ktime_get_raw(), ctxt->pause_start));
        ctxt->pause = false;
        break;
    }

    return 0;
}

static int vortex_mmap(struct file *file, struct vm_area_struct *vma) {
    struct vortex_ctxt *ctxt = file->private_data;
    unsigned long flags = vma->vm_flags;

    if (vma->vm_flags & (VM_WRITE | VM_EXEC))
        return -EPERM;

    flags |= VM_DONTEXPAND;
    flags &= ~(VM_MAYWRITE | VM_MAYEXEC);
    vm_flags_reset(vma, flags);
    vma->vm_private_data = ctxt;
    vma->vm_pgoff = PFN_DOWN((unsigned long)ctxt->data);
    vma->vm_ops = &vortex_vm_ops;
    return 0;
}

static vm_fault_t vortex_mmap_fault(struct vm_fault *vmf) {
    struct vm_area_struct *vma = vmf->vma;
    struct vortex_ctxt *ctxt = vma->vm_private_data;
    struct page *page;
    unsigned long addr = (unsigned long)vmf->address;

    if (addr < vma->vm_start || addr > vma->vm_end)
        return VM_FAULT_SIGBUS;

    if (!ctxt->data)
        return VM_FAULT_SIGBUS;

    page = virt_to_page(ctxt->data);
    get_page(page);
    vmf->page = page;
    return 0;
}

module_init(vortex_init);
module_exit(vortex_exit);