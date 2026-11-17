"""Host-side behavioral tests of C routines extracted from the actual RX profile."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'firmware-work/source-readonly/firmware'


def function(text, name):
    start = text.index('void ' + name + '(')
    return text[start:text.index('\n}', start)+2]


def run_c(source):
    with tempfile.TemporaryDirectory(prefix='tellstick-rx-test-') as temp:
        path = Path(temp)
        (path/'test.c').write_text(source)
        result = subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(path/'test.c'), '-o', str(path/'test')], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        subprocess.run([str(path/'test')], check=True, capture_output=True)


class ReadOnlyTests(unittest.TestCase):
    def test_exact_registration_and_oversize_rejection(self):
        actual = '\n'.join(line for line in (SOURCE/'localaccess.c').read_text().splitlines() if not line.startswith('#include'))
        run_c('''#include <assert.h>
#include <string.h>
#include <stddef.h>
typedef unsigned char BYTE;
typedef unsigned char UDP_SOCKET;
#define INVALID_UDP_SOCKET 255
static const unsigned char *input;
static size_t remaining;
static unsigned registrations;
static UDP_SOCKET UDPOpen(int a, void *b, int c) { (void)a; (void)b; (void)c; return 1; }
static size_t UDPIsGetReady(UDP_SOCKET s) { (void)s; return remaining; }
static void UDPGet(BYTE *ch) { *ch=*input++; --remaining; }
static void UDPDiscard(void) { remaining=0; }
void registerListener(void) { ++registrations; }
''' + actual + '''
static void receive(const char *s, size_t length) { input=(const unsigned char*)s; remaining=length; localAccessTask(); assert(remaining==0); }
int main(void) {
    char large[1024];
    receive("B:reglistener",13); assert(registrations==1);
    receive("B:reglistener",12); assert(registrations==1);
    receive("B:reglistenerX",14); assert(registrations==1);
    receive("4:send",6); assert(registrations==1);
    receive("A:disconnect",12); assert(registrations==1);
    receive("6:saveip",8); assert(registrations==1);
    memset(large,'X',sizeof(large)); memcpy(large,"B:reglistener",13);
    receive(large,sizeof(large)); assert(registrations==1);
    receive("B:reglistener",13); assert(registrations==2);
    return 0;
}
''')

    def test_outgoing_message_bounds_and_recovery(self):
        text = (SOURCE/'livemessage.c').read_text()
        routines = '\n'.join(function(text, name) for name in ('LMAppendChar','LMClear','LMAppendString','LMAppendRomString'))
        run_c('''#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef char BYTE;
typedef int BOOL;
#define TRUE 1
#define FALSE 0
#define ROM const
static char buffer[200];
static unsigned char bufferP;
static int state;
#define SM_CLEARED 0
static BOOL valid=TRUE;
static char btohexa_high(size_t x) { return "0123456789ABCDEF"[(x>>4)&15]; }
static char btohexa_low(size_t x) { return "0123456789ABCDEF"[x&15]; }
''' + routines + '''
int main(void) {
    unsigned i;
    char payload[198];
    LMClear();
    for(i=0;i<199;++i) LMAppendChar('A');
    assert(valid && strlen(buffer)==199 && buffer[199]==0);
    LMAppendChar('B'); assert(!valid && buffer[199]==0);
    LMClear(); assert(valid && buffer[0]==0);
    memset(payload,'x',196); payload[196]=0;
    LMAppendString(payload); assert(valid && strlen(buffer)==199);
    LMClear(); memset(payload,'x',197); payload[197]=0;
    LMAppendString(payload); assert(!valid && strlen(buffer)<200);
    LMClear(); LMAppendRomString("hello"); assert(valid && strcmp(buffer,"5:hello")==0);
    LMAppendChar(0); assert(!valid);
    return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
