/* Bounded pulse transport; timing derives from 41.666667 MHz Fosc.
 * Does not parse Telldus commands, write EEPROM, or alter configuration. */
#include <htc.h>
#include "TCPIP Stack/TCPIP.h"
#include "HardwareProfile.h"
#include "pwm.h"
#include "txcontrol.h"

static unsigned int reloads[160];
static unsigned char seen[16][4];
static unsigned char seenCount = 0, seenNext = 0;

static void transmitFrame(unsigned char count) {
    unsigned char i;
    unsigned int timer;
    for(i=0;i<count;++i) {
        timer=reloads[i];
        SENDER=(i & 1) ? 0 : 1;
        TMR1ON=0;
        TMR1H=(unsigned char)(timer>>8);
        TMR1L=(unsigned char)timer;
        TMR1IF=0;
        TMR1ON=1;
        while(!TMR1IF) {}
    }
    TMR1ON=0;
    SENDER=0;
}

unsigned char txControl(const unsigned char *packet, unsigned int length) {
    unsigned char count, repeats, gap, i, j, same, oldPwm;
    unsigned int duration;
    unsigned long total = 0;
    if(length==8 && packet[0]=='T' && packet[1]=='P' && packet[2]=='1' && packet[3]==0) { return 2; }
    if(length<13 || packet[0]!='T' || packet[1]!='X' || packet[2]!='1' || packet[3]!=0) { return 1; }
    repeats=packet[8]; gap=packet[9]; count=packet[10];
    if(!repeats || repeats>100 || gap>50 || !count || count>160 || length != 11u+2u*count) { return 1; }
    for(i=0;i<count;++i) {
        duration=((unsigned int)packet[11u+2u*i]<<8) | packet[12u+2u*i];
        if(!duration || duration>600) { return 1; }
        total+=duration;
        if(total>12000ul) { return 1; }
        reloads[i]=(unsigned int)(65536ul-(duration*625ul+3ul)/6ul);
    }
    for(i=0;i<seenCount;++i) {
        same=1;
        for(j=0;j<4;++j) { if(seen[i][j]!=packet[4+j]) { same=0; } }
        if(same) { return 0; }
    }
    /* All validation completes before any RF pin or timer changes. */
    TMR4ON=0;
    TMR4IF=0;
    oldPwm=TMR2IE;
    TMR2IE=0;
    TMR1IE=0;
    T1CON=0x80; /* RD16=1, internal instruction clock, prescale 1:1, timer off */
    SENDER=0;
    RX_ANT=0;
    TX_ANT=1;
    setTXPulses(2);
    for(i=0;i<repeats;++i) {
        transmitFrame(count);
        for(j=0;j<gap;++j) { __delay_ms(1); }
        ClrWdt();
    }
    SENDER=0;
    TX_ANT=0;
    RX_ANT=1;
    TMR1ON=0;
    TMR4IF=0;
    TMR4ON=1;
    TMR2IE=oldPwm;
    for(j=0;j<4;++j) { seen[seenNext][j]=packet[4+j]; }
    seenNext=(seenNext+1)&15;
    if(seenCount<16) { ++seenCount; }
    return 0;
}
