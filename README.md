


# Осматриваем образ #

Воспользовавшись `binwalk`, видим, что имеется `sh` скрипт по смещению `0x413000`. Этот скрипт проверяет активацию.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/binwalk.jpg">
</p>

Сломаем проверку активации с помощью hex-редактора и заставим скрипт исполнять наши команды. Обратите внимание на то, что
пришлось урезать строчку `activated` до `activ`, чтобы размер образа остался тем же. Образ назовем `target_broken_activation.iso`.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/broken_script.jpg">
</p>

Запускаем образ через qemu:

```console
sudo qemu-system-x86_64 target_broken_activation.iso --enable-kvm
```

Вводим `/bin/sh`, `uname -a`, `ls -la /dev/activate`, и узнаем, что наш дистрибутив - `Minimal Linux 5.0.11`

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/uname.jpg">
</p>

Итак, имеем:
1. Дистрибутив - `Minimal Linux`.
2. Проверкой почты, ключа занимается символьное устройство `/dev/activate`, а значит, логику проверки нужно искать где-то
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


# Поиск `register_chrdev`

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

Получается образ `src/minimal_linux_live.iso`.

Разархивируем его в папку `src/iso`.

В `src/iso/boot` теперь лежит архив ядра `kernel.xz`, само ядро `vmlinux` и рутовая файловая система `rootfs.xz`.

Посмотрим, что там в ядре.

Запускаем `qemu` в одном терминале:
```console
sudo qemu-system-x86_64 -kernel kernel.xz -initrd rootfs.xz -append nokaslr -s
```

В другом - `gdb`:
```console
sudo gdb vmlinux
(gdb) target remote localhost:1234
```

В другом терминале
```console
sudo sudo qemu-system-x86_64 -kernel kernel.xz -initrd rootfs.xz -append nokaslr -s
```
А теперь ищем `register_chrdev`
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/chrdev_regexp.jpg">
</p>

Очевидно, что наш вариант - это __register_chrdev.

Дизассемблируем:
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_disas.jpg">
</p>

Какую сигнатуру взять? Я попробовал несколько вариантов и остановился на следующем куске:

```asm
   0xffffffff811c9785 <+101>:	shl    $0x14,%esi
   0xffffffff811c9788 <+104>:	or     %r12d,%esi
```

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_sig.jpg">
</p>

Дело в том, что в `target` образе есть только одна функция, которая содержит `0xc1, 0xe6, 0x14, 0x44, 0x09, 0xe6`.

Сейчас покажу, но сначала узнаем, в каком сегменте ее искать.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/minimal_segments.jpg">
</p>

У функции `__register_chrdev` адрес `0xffffffff811c9720`, это сегмент `.text`. Там и будем искать.

Кстати, нужно оключить kaslr у целевого образа. Сделать это можно в hex-редакторе.

Просто ищем строчку `APPEND vga=normal` и меняем на `APPEND nokaslr\x20\x20\x20`.

Разархивируем в папку `iso`.

Извлекаем ядро из архива

```console
extract-vmlinux kernel.xz > vmlinux
```

Теперь в одном терминале:
```console
sudo gdb vmlinux
(gdb) target remote localhost:1234
```
В другом:
```console
sudo qemu-system-x86_64 target_nokaslr.iso -s -enable-kvm
```

Смотрим границы сегмента `.text`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/target_segments.jpg">
</p>

Границы `0xffffffff81000000 - 0xffffffff81600b91`, там и будем искать сигнатуру `0xc1, 0xe6, 0x14, 0x44, 0x09, 0xe6`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_sig_found.jpg">
</p>

Кусок найден по адресу `0xffffffff810dc643`. Но это только кусок, посмотрим, что выше:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_found.jpg">
</p>

А вот и начало функции `0xffffffff810dc5d0`.
