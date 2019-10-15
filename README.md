


# Осматриваем образ #

Воспользовавшись `binwalk`, видим, что имеется `sh` скрипт по смещению `0x413000`. Этот скрипт проверяет почту и ключ:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/binwalk.jpg">
</p>

Сломаем проверку с помощью hex-редактора прямо в образе и заставим скрипт исполнять наши команды. Как он теперь выглядит:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/broken_script.jpg">
</p>

Обратите внимание на то, что пришлось урезать строчку `activated` до `activ`, чтобы размер образа остался тем же. К счастью, проверки хэш-суммы нет. Образ назовем `lunix_broken_activation.iso`. 

Запускаем его через qemu:

```console
sudo qemu-system-x86_64 lunix_broken_activation.iso -enable-kvm
```

Покопаемся внутри: вводим `/bin/sh`, `uname -a`, `ls -la /dev/activate`.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/uname.jpg">
</p>

Итак, имеем:
1. Дистрибутив - `Minimal Linux 5.0.11`.
2. Проверкой почты, ключа занимается символьное устройство `/dev/activate`, а значит, логику проверки нужно искать где-то
в недрах ядра.
3. Почта, ключ передаются в формате `email|key`.

Образ `target_broken_activation.iso` нам более не потребуется.

# Символьные устройства и ядро

Такие устройства как `/dev/zero`, `/dev/null`, `/dev/activate` и т.д. регистрируются с помощь функции `register_chrdev`:

```c
int register_chrdev (unsigned int   major,
                     const char *   name,
                     const struct   fops);
```

`name` - имя, а структура `fops` содержит указатели на функции типа `read`/`write`:

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

Нас интересует только функция:
```c
ssize_t (*write) (struct file *, const char *, size_t, loff_t *);
```
Здесь второй аргумент - это буфер с переданными данными, следующий - размер буфера.


# Поиск `register_chrdev`

По умолчанию, `Minimal Linux` компилируется с отключенной отладочной информацией, чтобы уменьшить размер образа,
minimal же. Поэтому нельзя просто запустить отладчик и найти функцию по названию. Найти ее можно только по сигнатуре.

А сигнатуру можно взять из свежего образа `Minimal Linux` c включенной отладочной информацией.

То есть схема такая:

```
эталонный `Minimal Linux` -> известный адрес `register_chrdev` -> сигнатура -> искомый адрес `register_chrdev` в `Lunix`
```

## Готовим свежий образ `Minimal Linux`

1. Устанавливаем необходимые инструменты:
```console
sudo apt install wget make gawk gcc bc bison flex xorriso libelf-dev libssl-dev
```
2. Качаем скрипты:
```console
git clone https://github.com/ivandavidov/minimal
cd minimal/src
```
3. Корректируем `02_build_kernel.sh`:

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

Получается образ `minimal/src/minimal_linux_live.iso`.

## Еще немного приготовлений

Разархивируем `minimal_linux_live.iso` в папку `minimal/src/iso`.

В `minimal/src/iso/boot` лежат образ ядра `kernel.xz` и образ ФС `rootfs.xz`. Переименуем их в `kernel.minimal.xz`, `rootfs.minimal.xz`.

Помимо этого нужно вытащить ядро из образа. В этом поможет скрипт [extract-vmlinux](https://github.com/torvalds/linux/blob/master/scripts/extract-vmlinux):

```console
extract-vmlinux kernel.minimal.xz > vmlinux.minimal
```

Теперь в папке `minimal/src/iso/boot` у нас такой набор: `kernel.minimal.xz`, `rootfs.minimal.xz`, `vmlinux.minimal`.

А вот из `lunix.iso` нам нужно только ядро. Поэтому проводим все те же операции, ядро называем `vmlinux.lunix`, про `kernel.xz`, `rootfs.xz` забываем, сейчас расскажу почему. 

## Отключаем KASLR в `lunix.iso`

У меня получилось отключить `KASLR` в случае со свежесобранным `Minimal Linux` в `QEMU`.

Но не получилось с `Lunix`. Поэтому придется править сам образ.

Для этого откроем его в hex-редакторе, найдем строчку `APPEND vga=normal` и заменим на `APPEND nokaslr\x20\x20\x20`.

А образ назовем `lunix_nokaslr.iso`.

## Ищем и находим сигнатуру `register_chrdev`

Я напоминаю, что схема поиска такая:

```
эталонный `Minimal Linux` -> известный адрес `register_chrdev` -> сигнатура -> искомый адрес `register_chrdev` в `Lunix`
```

Запускаем в одном терминале свежий `Minimal Linux`:

```console
sudo qemu-system-x86_64 -kernel kernel.minimal.xz -initrd rootfs.minimal.xz -append nokaslr -s
```

В другом отладчик:
```console
sudo gdb vmlinux.minimal
(gdb) target remote localhost:1234
```

А теперь ищем `register_chrdev` в списке функций:
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/chrdev_regexp.jpg">
</p>

Очевидно, что наш вариант - это `__register_chrdev`.

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

Дело в том, что в `lunix` есть только одна функция, которая содержит `0xc1, 0xe6, 0x14, 0x44, 0x09, 0xe6`.

Сейчас покажу, но сначала узнаем, в каком сегменте ее искать.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/minimal_segments.jpg">
</p>

У функции `__register_chrdev` адрес `0xffffffff811c9720`, это сегмент `.text`. Там и будем искать.

Отключаемся от эталонного `Minimal Linux`. Подключаемся к `lunix` теперь.

В одном терминале:
```console
sudo qemu-system-x86_64 lunix_nokaslr.iso -s -enable-kvm
```
В другом:
```console
sudo gdb vmlinux.lunix
(gdb) target remote localhost:1234
```

Смотрим границы сегмента `.text`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/target_segments.jpg">
</p>

Границы `0xffffffff81000000 - 0xffffffff81600b91`, там и будем искать сигнатуру `0xc1, 0xe6, 0x14, 0x44, 0x09, 0xe6`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_sig_found.jpg">
</p>

Кусок находим по адресу `0xffffffff810dc643`. Но это только часть функции, посмотрим, что выше:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_found.jpg">
</p>

А вот и начало функции `0xffffffff810dc5d0`.
