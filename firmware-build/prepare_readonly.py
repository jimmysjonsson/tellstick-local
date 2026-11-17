"""Create an isolated receive-only research profile from the compatible baseline."""
from pathlib import Path
import shutil
import re

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / 'firmware-work/source'
dst = ROOT / 'firmware-work/source-readonly'
for sub in ('firmware', 'rf', 'tcpip/Include', 'tcpip/TCPIP Stack'):
    shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)


def edit(name, transform):
    path = dst / name
    path.write_text(transform(path.read_text()))

# Keep only registration and local-event delivery. Drop all command dispatch,
# RF send functions and network-write/reset entry points from this source unit.
edit('firmware/tellsticknet.c', lambda s: s[:s.index('\nvoid send()')] .replace('b = LMContent();', 'if (!LMIsValid()) { return; }\n\tb = LMContent();'))
# The sole accepted local datagram is exact, bounded listener registration.
(dst / 'firmware/localaccess.c').write_text('''#include <htc.h>
#include "TCPIP Stack/TCPIP.h"
#include <string.h>
#include "common.h"
#include "localaccess.h"
static const char request[] = "B:reglistener";
UDP_SOCKET localSocket;
void registerListener(void);
void localAccessTask(void) {
    static BYTE ready = 0;
    char message[sizeof(request)];
    BYTE ch, length = 0, overflow = 0;
    if (!ready) {
        localSocket = UDPOpen(42314, NULL, 42314);
        if (localSocket == INVALID_UDP_SOCKET) { return; }
        ready = 1;
    }
    if (!UDPIsGetReady(localSocket)) { return; }
    while (UDPIsGetReady(localSocket)) {
        UDPGet(&ch);
        if (length < sizeof(request)-1) { message[length++] = ch; }
        else { overflow = 1; }
    }
    UDPDiscard();
    if (!overflow && length == sizeof(request)-1 &&
        memcmp(message, request, sizeof(request)-1) == 0) { registerListener(); }
}
''')
# Retain receive sampling setup, but no RF activation or pulse code.
edit('firmware/rf.c', lambda s: s[:s.index('\nvoid activateTransmitter()')] + s[s.index('\nvoid initReceiver()'):s.index('\nvoid initTransmitter()')] + '''
void initTransmitter(void) {
    SENDER = 0;
    TX_ANT = 0;
    SENDER_TRIS = 0;
    TX_ANT_TRIS = 0;
    TMR1ON = 0;
    TMR1IE = 0;
    TMR3ON = 0;
    TMR3IE = 0;
    activateReceiver();
}
''')
# No timer-three RF ISR. Read only the six identity bytes, not secret/network data.
def main_source(s):
    s = re.sub(r'\n\tif \(TMR3IF\) \{.*?\n\t\}', '', s, flags=re.S)
    s = s.replace('loadEEPROM((unsigned char*)&config, sizeof(config));', 'memset(&config, 0, sizeof(config));\n\tloadEEPROM(config.MACAddr, sizeof(config.MACAddr));')
    start = s.index('\n\tif (config.ipAddr.byte.LB')
    end = s.index('\n}\n\nint main()', start)
    s = s[:start] + '''
    AppConfig.Flags.bIsDHCPEnabled = TRUE;
    AppConfig.Flags.bInConfigMode = TRUE;
    AppConfig.MyIPAddr = AppConfig.DefaultIPAddr;
    AppConfig.MyMask = AppConfig.DefaultMask;
    AppConfig.MyGateway.Val = MY_DEFAULT_GATE_BYTE1 | MY_DEFAULT_GATE_BYTE2<<8ul | MY_DEFAULT_GATE_BYTE3<<16ul | MY_DEFAULT_GATE_BYTE4<<24ul;
    AppConfig.PrimaryDNSServer.Val = MY_DEFAULT_PRIMARY_DNS_BYTE1 | MY_DEFAULT_PRIMARY_DNS_BYTE2<<8ul | MY_DEFAULT_PRIMARY_DNS_BYTE3<<16ul | MY_DEFAULT_PRIMARY_DNS_BYTE4<<24ul;
    AppConfig.SecondaryDNSServer.Val = 0;
''' + s[end:]
    # Set output latches low before changing direction to output.
    start = s.index('\n\tTRISA = 0;')
    end = s.index('\n\tOSCTUNE', start)
    s = s[:start] + '\n\tLATA=0; LATB=0; LATC=0; LATD=0; LATE=0; LATF=0; LATG=0;\n\tTRISA=0; TRISB=0; TRISC=0; TRISD=0; TRISE=0; TRISF=0; TRISG=0;\n' + s[end:]
    return s
edit('firmware/main.c', main_source)
# Compile out EEPROM write implementations.
edit('firmware/eeprom.c', lambda s: re.sub(r'void (?:clearEEPROM|saveEEPROM)\([^)]*\) \{.*?\n\}', '', s, flags=re.S))
edit('firmware/TCPIPConfig.h', lambda s: s.replace('#define STACK_USE_REBOOT_SERVER', '/* Remote reboot server disabled. */'))
edit('firmware/common.h', lambda s: s.replace('#define FIRMWARE_VERSION "X"', '#define FIRMWARE_VERSION "X-RX1"'))
edit('firmware/discovery.c', lambda s: s.replace('UDPPutString(config.secret);', 'UDPPutROMString(lite_public_marker);').replace('void discoveryTask()', 'static const char lite_public_marker[] = "LOCALONLY";\n\nvoid discoveryTask()'))
# Fail closed on outgoing message overflow, retaining NUL termination.
def message_source(s):
    s = s.replace('static char buffer[200];', 'static char buffer[200];\nstatic BOOL valid = TRUE;\nBOOL LMIsValid(void) { return valid; }')
    a = s.index('void LMAppendChar('); b = s.index('\nvoid LMClear()', a)
    s = s[:a] + '''void LMAppendChar(const char ch) {
    unsigned int n = strlen(buffer);
    if (!valid || n >= sizeof(buffer)-1 || ch == 0) { valid = FALSE; return; }
    buffer[n] = ch;
    buffer[n+1] = 0;
}
''' + s[b:]
    s = s.replace("memset(&buffer, '\\0', sizeof(buffer));", "memset(&buffer, '\\0', sizeof(buffer));\n\tvalid = TRUE;")
    s = s.replace('strcat(&buffer, string);', '''if (!valid || strlen(buffer) + strlen(string) >= sizeof(buffer)) {
        valid = FALSE;
        return;
    }
    strcat(buffer, string);''')
    return s
edit('firmware/livemessage.c', message_source)
edit('firmware/livemessage.h', lambda s: s + '\nBOOL LMIsValid(void);\n')
print('Prepared receive-only source; nothing uploaded.')
