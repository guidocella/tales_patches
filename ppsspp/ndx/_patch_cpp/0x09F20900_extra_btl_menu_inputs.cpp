//compiler options used:
//-mno-abicalls -march=allegrex -mabi=eabi -G0  -fomit-frame-pointer
#include <stdint.h>

extern "C" void pos_0x09F10800(unsigned int pID); //cycle ctrl mode
extern "C" void pos_08820FA4(uintptr_t MainPtr); //cycle control chars

extern "C" unsigned int  get_btn_0x4850(unsigned int mask, unsigned int index); //0x09F20700 fnc
extern "C" void* z_un_09F00D00(int index); // get_char_by_index

void btl_menu_extra_input_checks()
{
    uintptr_t mainPtr = 0x08AF1F30;

    uint8_t gameState = *(uint8_t*)(mainPtr+0x5ED);

    if( !(gameState == 0x0F || gameState == 0x17) ) return; //return if not btl menu or pause

    uintptr_t cMemPtr = 0x081E0000;

    uint32_t menuOwner = *(uint32_t*)(cMemPtr+0x4);
    uint8_t partySize = *(uint8_t*)(mainPtr+0x5f4);

    uint16_t selButtonBind = *(uint16_t*)(mainPtr+0x2e);
    uint16_t lButtonBind = *(uint16_t*)(mainPtr+0x42);

    //while the focus owner's pad struct is swapped into pad 1's (0x09F00000 focus), their pads are swapped too
    uint32_t swapped = *(uint32_t*)(cMemPtr+0x58);

    for(int i = 0; i < partySize; i++)
    {
        unsigned int pad = i;
        if(swapped != 0 && i == 0) pad = swapped;
        else if(swapped != 0 && i == swapped) pad = 0;

        int bMask = get_btn_0x4850(0,pad);

        //char cycle
        if( (bMask&lButtonBind)!=0 )
        {
            pos_08820FA4(i);
        }

        //past this point - everyone EXCEPT menu host
        //if(i == menuOwner) continue; //skip the person who opened the menu because they already have these controls
        //fuck it rip out the original

        //mode change
        if( (bMask&selButtonBind)!=0 )
        {
            pos_0x09F10800(i);
        }
    }
}