#!/usr/bin/env python3
# Assembles _patch_txt/*.txt (armips syntax, as pasted into PPSSPP's "Assemble from Clipboard"), compiles
# _patch_cpp/*.cpp, and writes them with the hooks below as CWCheat codes.
# Usage: build.py [ARMIPS] > ../NDX-MP.ini
# armips (default ~/.local/src/armips-build/armips): cmake /opt/ppsspp/ext/armips && make armips-bin (PPSSPP assembles with the same one). Also needs clang, ld.lld.
import os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ARMIPS = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/.local/src/armips-build/armips')

# Superseded or not code
SKIP = {
    '0x08820FA4_cycle_control_characters_new.txt',  # gcc output of the old .cpp, which read the player from 0x081E0004
    '0x0_cycle_control_characters_old.txt',
    '0x09F20500_mim_tst.txt',  # older version of 0x09F20500_block_commands_to_manual_characters.txt
    'stackframetemplate.txt',
    '0x08820FA4_cycle_control_characters.cpp',  # replaced by _upd.cpp
}

# Symbols the sources use that PPSSPP's symbol map resolved (z_un_XXXXXXXX and pos_XXXXXXXX are plain addresses)
NAMED = {'sceVfpuScalarSin': 0x0897AD5C}

SYM = re.compile(r'\b(?:z_un_|pos_|pos_0x|get_btn_0x)([0-9A-Fa-f]{4,8})\b')


def symbols(src):
    syms = {}
    for m in SYM.finditer(src):
        name, addr = m.group(0), int(m.group(1), 16)
        if name.startswith('get_btn_0x'):  # extra_btl_menu_inputs.cpp: get_btn_0x4850 lives at 0x09F20700
            addr = 0x09F20700
        syms[name] = addr
    for name, addr in NAMED.items():
        if re.search(r'\b%s\b' % name, src):
            if addr is None:
                sys.exit(f'{name}: address unknown')
            syms[name] = addr
    return syms


# Game code redirected into the payloads, per cheat: (address, armips, comment)
FIXES = [
    (0x0881650C, 'j 0x09F20200 :: nop', 'more_mimic_fail_conds'),
    (0x08816830, 'j 0x09F20850 :: nop', 'ob_activation_self_timestop_fix'),
    (0x08857F08, 'j 0x09F02100 :: nop', 'mimic_self_use_fix_v2'),
]
# The 8 input wrappers at 0x08812740-0x08812928 each call a digital and an analog getter
WRAPPERS = [
    (0x0881274C, 0x09F00300), (0x08812764, 0x09F10B68), (0x08812790, 0x09F00370), (0x088127A8, 0x09F10B9C),
    (0x088127D4, 0x09F00350), (0x088127EC, 0x09F10C04), (0x08812818, 0x09F00340), (0x08812830, 0x09F10BD0),
    (0x0881285C, 0x09F10B68), (0x08812878, 0x09F00300), (0x088128A4, 0x09F10B9C), (0x088128C0, 0x09F00370),
    (0x088128EC, 0x09F10C04), (0x08812908, 0x09F00350), (0x08812934, 0x09F10BD0), (0x08812950, 0x09F00340),
]
COOP = [
    (0x088E92B8, 'jal 0x09F00000', 'extra_pad_update: read pads 2-4 from 0x0E000000'),
    (0x088E9488, 'j 0x09F000A0 :: nop', 'extra_pad_update: update pads 2-4 after pad 1'),
    *[(a, f'jal 0x{t:08X}', 'input wrapper -> pad of player 0x081E0004') for a, t in WRAPPERS],
    (0x08817630, 'j 0x09F10000 :: nop', 'FUN_08817630 -> sync_battle_status'),
    (0x08817B18, 'j 0x09F00600 :: nop', 'update_btl_ctrl_from_nonbtl'),
    (0x0888F7C4, 'j 0x09F00800 :: nop', 'display_ctrl_mode_ui'),
    (0x0888F34C, 'j 0x09F20600 :: nop', 'raise_reserve_text_for_control_disp'),
    (0x088147E4, 'j 0x09F20880 :: nop', 'entry_to_extra_btl_menu_inputs'),
    (0x0881460C, 'jal 0x09F10500 :: nop :: b 0x08814718 :: nop', 'input_check_etc_battle (target/pause/select)'),
    (0x08849674, 'jal 0x09F10A00', 'shortcut_encapsulator'),
    (0x088670CC, 'jal 0x09F00E40', 'shortcut update: char of the player whose pad is read, not player 1'),
    (0x08867004, 'jal 0x09F01400', 'shortcut_patchcode'),
    (0x08867030, 'jal 0x09F01400', 'shortcut_patchcode'),
    (0x0886705C, 'jal 0x09F01400', 'shortcut_patchcode'),
    (0x08867088, 'jal 0x09F01400', 'shortcut_patchcode'),
    (0x0887F2A8, 'jal 0x09F10D00', 'update_target_cursor_in_draw_loop'),
    (0x08847A68, 'jal 0x09F20000 :: nop :: b 0x08847AA8 :: nop', 'main_btl_input_loop'),
    (0x08848C54, 'j 0x09F00E00 :: nop', 'input_char_is_players'),
    (0x0881C06C, 'j 0x09F00F00 :: nop', 'camera_frame_players'),
    (0x08813D0C, 'jal 0x09F01C00', 'in_battle_flag: set every battle frame'),
    (0x0881379C, 'j 0x09F01C20 :: nop', 'in_battle_flag: cleared by the battle teardown'),
    (0x0889E340, 'nop', 'menu exit no longer sets party members 2-4 back to auto'),
    *[(a, 'nop', 'arte menu: START (shortcut settings) on every party member page, not only the first')
      for a in (0x0889CD0C, 0x0889CFD8, 0x0889D330)],
    (0x088145AC, 'b 0x0881460C :: nop', 'player 1 menu check -> input_check_etc_battle, for every player'),
    (0x08814EF8, 'nop', 'menu L for player 1 -> extra_btl_menu_inputs, for every player'),
    (0x08814F4C, 'nop', 'menu select for player 1 -> extra_btl_menu_inputs, for every player'),
    (0x0886731C, 'j 0x09F20500 :: nop', 'block_commands_to_manual_characters'),
]
# Also used by the co-op code, so in both cheats
SHARED_FILES = {'0x9F01900_get_closest_chara_func-MEEBO.txt'}
FIX_FILES = {
    '0x09F20200_more_mimic_fail_conds.txt',
    '0x09F20850_ob_activation_self_timestop_fix.txt',
    '0x9F01900_get_closest_chara_func-MEEBO.txt',
    '0x9F02100_mimic_self_use_fix_v2-MEEBO.txt',
}

HEADER = '''_G Tales of Phantasia: Narikiri Dungeon X [JP]
# Generated by ndx/build.py from ndx/_patch_txt and ndx/_patch_cpp. Needs the ppsspp-tales-mp fork for _M.
_M TOP_NARIKIRI_DUNGEON_R'''

FIXES_NAME = 'NDX mimic and OB activation fixes'
COOP_NAME = '''NDX co-op
# Pads 2-4 are PPSSPP's virtual pads (Settings > Controls > Virtual Extra Pads).
# Not per player: the stick position getters 0x088E9560/9570 (analog_checker_replacements thing_1/2)'''


def assemble_src(addr, body, tmp, what):
    out = os.path.join(tmp, 'out.bin')
    asm = ['.psp', f'.create "{out}",0x{addr:08X}']
    asm += [f'.definelabel {n},0x{a:08X}' for n, a in symbols(body).items()]
    # armips lets .org move backwards over code already assembled
    body = re.sub(r'^\s*\.org\s+(0x[0-9A-Fa-f]+)', r'.if org() > \1\n.error "code before .org \1 runs into it"\n.endif\n.org \1',
                  body, flags=re.M)
    asm += [body, '.close', '']
    s = os.path.join(tmp, 'in.asm')
    open(s, 'w').write('\n'.join(asm))
    r = subprocess.run([ARMIPS, s], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'{what}:\n{r.stdout}{r.stderr}')
    return open(out, 'rb').read()


def assemble(path, tmp):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'^\s*address:\s*(0x[0-9A-Fa-f]+)', src, re.M)
    if not m:
        sys.exit(f'{path}: no address: line')
    addr = int(m.group(1), 16)
    body = src[m.end():]
    body = re.sub(r'0x-([0-9A-Fa-f]+)', r'-0x\1', body)  # addi s5,s5,0x-1
    if os.environ.get('TEST') and os.path.basename(path).startswith('0x09F00000_'):
        # all 4 pads read from 0x081F0000 + 0x10 * pad, where work/pad.mjs writes
        body = body.replace('lui\tt0,0xE00', 'lui\tt0,0x81F').replace('j\t0x089830BC', 'j\textra_pad')
    return addr, assemble_src(addr, body, tmp, path)


def compile_cpp(path, tmp):
    name = os.path.basename(path)
    addr = int(name.split('_')[0], 16)
    src = open(path, encoding='utf-8').read()
    obj, elf, out = (os.path.join(tmp, f) for f in ('c.o', 'c.elf', 'c.bin'))
    # Allegrex is MIPS II plus extensions. clang has no EABI, but with <= 4 register arguments and no varargs o32
    # passes them the same way.
    subprocess.run(['clang', '--target=mipsel-unknown-elf', '-march=mips2', '-mno-abicalls', '-fno-pic', '-G0',
                    '-O2', '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-asynchronous-unwind-tables',
                    '-c', path, '-o', obj], check=True)
    subprocess.run(['llvm-objcopy', '--set-section-alignment', '.text=4', obj], check=True)
    defs = [f'--defsym={n}=0x{a:08X}' for n, a in symbols(src).items()]
    subprocess.run(['ld.lld', '-e', '0', f'-Ttext=0x{addr:08X}', *defs, obj, '-o', elf], check=True)
    subprocess.run(['llvm-objcopy', '-O', 'binary', '-j', '.text', elf, out], check=True)
    # lld rounds -Ttext up to .text's alignment, which would shift every absolute j target
    m = re.search(r'\.text\s+[0-9a-f]+\s+([0-9a-f]+)', subprocess.run(['llvm-objdump', '-h', elf], capture_output=True,
                                                                     text=True).stdout)
    if int(m.group(1), 16) != addr:
        sys.exit(f'{path}: .text linked at 0x{m.group(1)}, not 0x{addr:08X}')
    data = open(out, 'rb').read()
    for f in ('.rodata', '.data', '.bss', '.sdata', '.sbss'):
        r = subprocess.run(['llvm-objdump', '-h', elf], capture_output=True, text=True).stdout
        if re.search(r'\s%s\s+[0-9a-f]*[1-9a-f]' % re.escape(f), r):
            sys.exit(f'{path}: has a {f} section, which is not placed')
    return addr, data


def lines(addr, data):
    assert len(data) % 4 == 0
    for o in range(0, len(data), 4):
        a = addr + o
        yield f'_L 0x{0x20000000 | (a - 0x08800000):08X} 0x{struct.unpack_from("<I", data, o)[0]:08X}'


def main():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for d, f in [('_patch_txt', assemble), ('_patch_cpp', compile_cpp)]:
            for name in sorted(os.listdir(os.path.join(HERE, d))):
                if name in SKIP:
                    continue
                addr, data = f(os.path.join(HERE, d, name), tmp)
                out.append((addr, len(data), name, list(lines(addr, data))))
        hooks = {id(h): [(a, list(lines(a, assemble_src(a, asm.replace('::', '\n'), tmp, comment))), asm, comment)
                         for a, asm, comment in h] for h in (FIXES, COOP)}
    out.sort()
    for i, (a, n, name, _) in enumerate(out):
        for b, _, other, _ in out[i + 1:]:
            if a + n > b:
                sys.exit(f'{name} (0x{a:08X}-0x{a + n - 1:08X}) overlaps {other} (0x{b:08X})')
    print(HEADER)
    for title, files, h in [(FIXES_NAME, lambda n: n in FIX_FILES, FIXES),
                            (COOP_NAME, lambda n: n not in FIX_FILES or n in SHARED_FILES, COOP)]:
        print(f'\n_C0 {title}')
        for a, n, name, ls in out:
            if files(name):
                print(f'# {name}: 0x{a:08X}-0x{a + n - 1:08X}')
                print('\n'.join(ls))
        print('# hooks')
        for a, ls, asm, comment in hooks[id(h)]:
            print(f'# 0x{a:08X}: {asm.replace(" :: ", "; ")} ({comment})')
            print('\n'.join(ls))


main()
