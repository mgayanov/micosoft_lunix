


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

`name` - имя, а структура `fops` содержит указатели на функции драйвера:

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

[Нас не смущает, что искали `register_chrdev`, а нашли `__register_chrdev`](https://github.com/torvalds/linux/blob/298fb76a5583900a155d387efaf37a8b39e5dea2/include/linux/fs.h#L2673)

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

Границы `0xffffffff81000000 - 0xffffffff81600b91`, ищем `0xc1, 0xe6, 0x14, 0x44, 0x09, 0xe6`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_sig_found.jpg">
</p>

Кусок находим по адресу `0xffffffff810dc643`. Но это только часть функции, посмотрим, что выше:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/reg_chrdev_found.jpg">
</p>

А вот и начало функции `0xffffffff810dc5d0`(`retq` - это выход из соседней функции).

# Поиск fops от /dev/activate и функции `write`

Прототип функции 

```c
int register_chrdev (unsigned int   major,
                     const char *   name,
                     const struct   fops);
```



Ставим брейк на `0xffffffff810dc5d0`.

Брейк сработает несколько раз. Это просыпаются устройства `mem`, `vcs`, `cpu/msr`, `cpu/cpuid`, а сразу за ними и наш `activate`.

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/activate_dev_found.jpg">
</p>

То, что указатель на имя хранится в регистре `rcx`, я выяснил простым перебором. А указатель на fops - в `r8`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/fops.jpg">
</p>

<details><summary>Напоминаю структуру fops</summary>

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

</details>

Итак, адрес функции `write` `0xffffffff811f068f`.

# Изучаем `write`

## Хэш функция

Откроем IDA, загрузим ядро и посмотрим, что внутри функции `write`.

Первыми обращают на себя внимание блоки:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/ida_sum_hash.jpg">
</p>

Здесь вызывается какая-то функция `sub_FFFFFFFF811F0413`, которая начинается так:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_table.jpg">
</p>

А по адресу `0xffffffff81829ce0` обнаруживается таблица для `sha256`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_table2.jpg">
</p>

То есть `sub_FFFFFFFF811F0413` = `sha256` Байты, хэш которых нужно получить, передаются через `$sp+0x50+var49`, а результат сохраняется по адресу `$sp+0x50+var48`.  Кстати, `var49=-0x49`, `var48=-0x48`, так что `$sp+0x50+var49` = `$sp+0x7`, `$sp+0x50+var48` = `$sp+0x8`.

Проверим.

Запускаем `qemu`, `gdb`, ставим брейк на`0xffffffff811f0748 call sub_FFFFFFFF811F0413` и на инструкцию `0xffffffff811f074d xor     ecx, ecx` после, вводим почту `test@mail.ru`, пароль `1234-5678-0912-3456`.

В функцию передается байт почты, а результат такой:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_t.jpg">
</p>

```python
>>> import hashlib
>>> hashlib.sha256(b"t").digest().hex()
'e3b98a4da31a127d4bde6e43033f66ba274cab0eb7eb1c70ec41402bf6273dd8'
>>>
```

То есть да, это действительно `sha256`, только она вычисляет хэши по всем байтам почты, а не один хэш только от почты.

Дальше хэши суммируются по-байтно. Но если сумма больше `0xEC`, то сохраняется остаток от деления на `0xEC`.

```python

import hashlib

def get_email_hash(email):
	
	h = [0]*32

	for sym in email:
		
		sha256 = hashlib.sha256(sym.encode()).digest()
		for i in range(32):
			s = h[i] + sha256[i]

			if s <= 0xEC:
				h[i] = s
			else:
				h[i] = s % 0xEC
	return h
```

Сумма сохраняется по адресу `0xFFFFFFFF81C82F80`.

Давайте посмотрим, какой будет хэш от почты `test@mail.ru`.

Ставим брейк на `0xFFFFFFFF811F0789`, это выход из циклов:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/test_final_hash.jpg">
</p>

И проверяем:
```python
>>> get_email_hash('test@mail.ru')
2b902daf5cc483159b0a2f7ed6b593d1d56216a61eab53c8e4b9b9341fb14880
```


<details><summary>raw</summary>
Перезапускаем

Ставим брейк на `0xffffffff811f068f`.

Вводим почту test@mail.ru

Пароль 1234-5678-0912-3456

Пробежавшись по регистрам, я увидел, что данные передаются через регистр `rsi`:

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/write_rsi.jpg">
</p>

Ставим брейк на чтение `rsi`, в моем случае это `0x557d32a7ca90`

Брейк срабатывает на инструкции `0xffffffff813b26dc`

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/first_break.jpg">
</p>

*(rdi) = *(rsi) 0xffff8880077d5e60

Брейк на rdi

Остановка
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/2_break.jpg">
</p>

Проверка на нули, т.к. rax = 0

Следующая остановка `0xffffffff811f083c`

Я открыл функцию write в ida

Там много всего, проверка на нули, парсинг почты, ключа и т.д.

Мое внимание привлек этот кусок

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/ida_susp_func.jpg">
</p>

Это адрес `FFFFFFFF811F0748`

Во-первых, что еще за функция, и во-вторых что за аргументы?
Ставим брейк на FFFFFFFF811F0748

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/susp_func_rsi_rdi.jpg">
</p>

Первый байт почты, и нули

Заглянем внутрь функции

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_table.jpg">
</p>

Меня привлекла инструкция
```asm
mov     rsi, offset unk_FFFFFFFF81829CE0
```

Узнаем, что в `FFFFFFFF81829CE0`

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_table2.jpg">
</p>

А это таблица для вычисления sha256

Предположим, что функция вычисляет хэш для каждого байта, а что в буфере(второй аргумент)?

Сейчас мы на FFFFFFFF811F0748

Позволим функции завершиться и остановимся сразу после: FFFFFFFF811F074D
<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/hash_t.jpg">
</p>

```python
>>> import hashlib
>>> hashlib.sha256(b"t").digest().hex()
'e3b98a4da31a127d4bde6e43033f66ba274cab0eb7eb1c70ec41402bf6273dd8'
>>>
```



В общем это хэш от байта

Посмотрим, какие аргументы будут переданы в следующий раз и что будет на выходе



<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/ida_sum_hash.jpg">
</p>

Хэши складываются по байтно, если сумма > 0xEC, то % 0xEC. Сохраняется в `FFFFFFFF81C82F80`

Проверим, ставим брейк на FFFFFFFF811F0748


<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/sum2hash.jpg">
</p>

Второй символ `e`
```python
>>> hashlib.sha256(b"e").digest().hex()
'3f79bb7b435b05321651daefd374cdc681dc06faa65e374e38337b88ca046dea'
```

А конечный хэш можно узнать на адресе FFFFFFFF811F0789, это выход из циклов

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/test_final_hash.jpg">
</p>

<p align="center">
	<img src="https://github.com/mgayanov/micosoft_lunix/blob/master/img/last_op.jpg">
</p>
</datails>



