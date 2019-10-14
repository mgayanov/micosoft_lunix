


# Осматриваем образ #

Воспользовавшись binwalk, видно, что имеется sh скрипт по смещению 0x413000. Этот скрипт проверяет активацию.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/binwalk.jpg">
</p>

Сломаем проверку активации с помощью hex-редактора и заставим скрипт исполнять наши команды. Обратите внимание на то, что
пришлось урезать строчку `activated` до `activ`, чтобы размер образа остался тем же.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/broken_script.jpg">
</p>

Запускаем образ через qemu, вводим /bin/sh, uname -a, и узнаем, что наш дистрибутив - Minimal Linux 5.0.11

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/uname.jpg">
</p>

Итак, имеем:
1. Дистрибутив - `Minimal Linux`.
2. Проверкой почты, ключа занимается символьное устройство `/dev/activate`, а значит, логику проверку нужно искать где-то
в недрах ядра.
3. Почта, ключ передаются в формате `email|key`.

Образ `target_broken_activation.iso` нам более не потребуется.

# Символьные устройства и ядро

Такие устройства как `/dev/zero`, `/dev/null`, `/dev/activate` регистрируются с помощь функции `register_chrdev`

```c
int register_chrdev (unsigned int   major,
                     const char *   name,
                     const struct   fops);
```

`name` - имя, а структура `fops` содержит указатели на функции типа чтение/запись:

```c
struct file_operations {
       struct module *owner;
       loff_t (*llseek) (struct file *, loff_t, int);
       ssize_t (*read) (struct file *, char *, size_t, loff_t *);
       ssize_t (*write) (struct file *, const char *, size_t, loff_t *);
       int (*readdir) (struct file *, void *, filldir_t);
       unsigned int (*poll) (struct file *, struct poll_table_struct *);
       int (*ioctl) (struct inode *, struct file *, unsigned int, unsigned long);
       int (*mmap) (struct file *, struct vm_area_struct *);
       int (*open) (struct inode *, struct file *);
       int (*flush) (struct file *);
       int (*release) (struct inode *, struct file *);
       int (*fsync) (struct file *, struct dentry *, int datasync);
       int (*fasync) (int, struct file *, int);
       int (*lock) (struct file *, int, struct file_lock *);
    ssize_t (*readv) (struct file *, const struct iovec *, unsigned long,
          loff_t *);
    ssize_t (*writev) (struct file *, const struct iovec *, unsigned long,
          loff_t *);
    };
```

Нас интересует только функция
```c
ssize_t (*write) (struct file *, const char *, size_t, loff_t *);
```
Здесь второй аргумент - это буфер с переданными данными, следующий - размер буфера.


# Поиск `register_chr_dev`

По умолчанию, образ `Minimal Linux` компилируется с отключенной отладочной информацией, чтобы уменьшить размер образа,
minimal же. Поэтому нельзя просто запустить отладчик и найти функцию по названию. Найти ее можно только по сигнатуре.

Но если мы соберем свой образ `Minimal Linux` со всеми названиями функций, то сможем найти там `register_chr_dev` и сигнатуру.
Поэтому займемся этим.

1. Устанавливаем необходимые инструменты
```console
sudo apt install wget make gawk gcc bc bison flex xorriso libelf-dev libssl-dev
```
2. Качаем скрипты
```console
git clone https://github.com/ivandavidov/minimal
cd src
```
3. Корректируем `02_build_kernel.sh`
Это удаляем
```
  # Disable debug symbols in kernel => smaller kernel binary.
  sed -i "s/^CONFIG_DEBUG_KERNEL.*/\\# CONFIG_DEBUG_KERNEL is not set/" .config
```
Это добавляем
```
echo "CONFIG_GDB_SCRIPTS=y" >> .config
```
4. Компилируем
```console
./build_minimal_linux_live.sh
```

Скомпилированное ядро находится в `minimal/src/work/kernel/linux-5.2.12/vmlinux`, а `iso` образ в `src/minimal_linux_live.iso`.

Разархивируем `minimal_linux_live.iso` в папку `src/iso`.

В `src/iso/boot` лежит ядро `kernel.xz` и рутовая файловая система `rootfs.xz`.

Запускаем qemu, gdb

```
sudo gdb vmlinux
(gdb) target remote localhost:1234
```

В другом терминале
```
sudo sudo qemu-system-x86_64 -kernel kernel.xz -initrd rootfs.xz -append nokaslr -s
```

Сходу `register_chr_dev` мы не найдем, потому что сигнатура у нее ничем не примечательна.

Но мы можем найти `chr_dev_init`, которая вызывает `register_chr_dev`.

Ищем сигнатуру `chr_dev_init`

```

(gdb) info functions chr_dev_init
All functions matching regular expression "chr_dev_init":

Non-debugging symbols:
0xffffffff829e2cc6  chr_dev_init
(gdb) disas chr_dev_init
Dump of assembler code for function chr_dev_init:
   0xffffffff829e2cc6 <+0>:	push   %rbx
   0xffffffff829e2cc7 <+1>:	xor    %esi,%esi
   0xffffffff829e2cc9 <+3>:	mov    $0xffffffff8206fdc0,%r8
   0xffffffff829e2cd0 <+10>:	mov    $0xffffffff821d7e2e,%rcx
   0xffffffff829e2cd7 <+17>:	mov    $0x100,%edx
   0xffffffff829e2cdc <+22>:	mov    $0x1,%edi
   0xffffffff829e2ce1 <+27>:	callq  0xffffffff811c9720 <__register_chrdev>
   0xffffffff829e2ce6 <+32>:	test   %eax,%eax
```
Инструкции +17 и +22 выглядят уникальными, посмотрим байты

```
(gdb) x/6bx chr_dev_init+17
0xffffffff829e2cd7 <chr_dev_init+17>:	0xba	0x00	0x01	0x00	0x00	0xbf
```


