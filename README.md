# micosoft_lunix


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



# Поиск register_chr_dev #

Найти `register_chr_dev` можно по сигнатуре. А чтобы узнать сигнатуру, скомпилируем новое ядро с включенной отладочной
информацией. 

Компилировать будем такое же ядро, как и в задании, - Minimal Linux Live.

1. Устанавливаем необходимые инструменты
```
sudo apt install wget make gawk gcc bc bison flex xorriso libelf-dev libssl-dev
```
2. Качаем скрипты
```
git clone https://github.com/ivandavidov/minimal
cd src
```
3. Находим и удаляем в `02_build_kernel.sh`
```
  # Disable debug symbols in kernel => smaller kernel binary.
  sed -i "s/^CONFIG_DEBUG_KERNEL.*/\\# CONFIG_DEBUG_KERNEL is not set/" .config
```
4. Добавляем в `02_build_kernel.sh`
```
echo "CONFIG_GDB_SCRIPTS=y" >> .config
```
5. Компилируем
```
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


