


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
```
sudo gdb vmlinux
(gdb) target remote localhost:1234
```

В другом терминале
```
sudo sudo qemu-system-x86_64 -kernel kernel.xz -initrd rootfs.xz -append nokaslr -s
```
А теперь ищем `register_chrdev`
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/uname.jpg">
</p>
```


