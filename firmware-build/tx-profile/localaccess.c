#include <htc.h>
#include "TCPIP Stack/TCPIP.h"
#include <string.h>
#include "common.h"
#include "localaccess.h"
#include "txcontrol.h"
static const char registration[] = "B:reglistener";
static unsigned char packet[340];
UDP_SOCKET localSocket;
void registerListener(void);
void localAccessTask(void) {
    static BYTE ready=0;
    unsigned int length=0;
    unsigned char ch, overflow=0, status, i;
    if(!ready) {
        localSocket=UDPOpen(42314,NULL,42314);
        if(localSocket==INVALID_UDP_SOCKET) { return; }
        ready=1;
    }
    if(!UDPIsGetReady(localSocket)) { return; }
    while(UDPIsGetReady(localSocket)) {
        UDPGet(&ch);
        if(length<sizeof(packet)) { packet[length++]=ch; }
        else { overflow=1; }
    }
    UDPDiscard();
    /* Narrow LAN source allowlist; not cryptographic authentication. */
    if(overflow || UDPSocketInfo[localSocket].remote.remoteNode.IPAddr.v[0]!=192 ||
        UDPSocketInfo[localSocket].remote.remoteNode.IPAddr.v[1]!=168 ||
        UDPSocketInfo[localSocket].remote.remoteNode.IPAddr.v[2]!=1 ||
        UDPSocketInfo[localSocket].remote.remoteNode.IPAddr.v[3]!=149) { return; }
    if(length==sizeof(registration)-1 && memcmp(packet,registration,sizeof(registration)-1)==0) {
        registerListener(); return;
    }
    if(length<8 || packet[0]!='T' || packet[2]!='1' || packet[3]!=0 ||
        (packet[1]!='X' && packet[1]!='P')) { return; }
    status=txControl(packet,length);
    if(!UDPIsPutReady(localSocket)) { return; }
    UDPPut('T'); UDPPut('A'); UDPPut('1'); UDPPut(0);
    for(i=4;i<8;++i) { UDPPut(packet[i]); }
    UDPPut(status);
    UDPFlush();
}
