// Single-player network stub for the PSP MVP.
#include "network.h"
#include "mmulti.h"
#include "blood.h"
#include "globals.h"
#include "levels.h"

#include <string.h>

char packet[576];
bool gStartNewGame = false;
PACKETMODE gPacketMode = PACKETMODE_0;
ClockTicks gNetFifoClock = 0;
int gNetFifoTail = 0, gNetFifoHead[8], gPredictTail = 0, gNetFifoMasterTail = 0;
GINPUT gFifoInput[256][8];
int myMinLag[8], otherMinLag = 0, myMaxLag = 0;
unsigned int gChecksum[4], gCheckFifo[256][8][4];
int gCheckHead[8], gSendCheckTail = 0, gCheckTail = 0, gInitialNetPlayers = 1, gBufferJitter = 0, gPlayerReady[8];
bool bNoResend = true, gRobust = false, bOutOfSync = false, ready2send = false;
NETWORKMODE gNetMode = NETWORK_NONE;
char gNetAddress[32];
int gNetPort = kNetDefaultPort;
PKT_STARTGAME gPacketStartGame;

void netResetToSinglePlayer(void)
{
    // Keep every traversal of connectpoint2 inside the sole local player.
    // The regular network backend initializes this in netResetToSinglePlayer;
    // an all-zero static array instead describes an invalid 0 -> 0 loop.
    myconnectindex = connecthead = 0;
    gInitialNetPlayers = gNetPlayers = numplayers = 1;
    for (int i = 0; i < kMaxPlayers; ++i)
        connectpoint2[i] = -1;
    gGameOptions.nGameType = 0;
    gNetMode = NETWORK_NONE;
}

void netResetState(void)
{
    netResetToSinglePlayer();
    gNetFifoClock = gFrameClock = totalclock = 0;
    gNetFifoMasterTail = 0;
    gPredictTail = 0;
    gNetFifoTail = 0;
    memset(gNetFifoHead, 0, sizeof(gNetFifoHead));
    memset(gCheckFifo, 0, sizeof(gCheckFifo));
    memset(myMinLag, 0, sizeof(myMinLag));
    otherMinLag = 0;
    myMaxLag = 0;
    memset(gCheckHead, 0, sizeof(gCheckHead));
    gSendCheckTail = 0;
    gCheckTail = 0;
    bOutOfSync = false;
    gBufferJitter = 1;
}
void netBroadcastMessage(int, const char *) {}
void netWaitForEveryone(char) {}
void sub_7AC28(const char *) {}
void netGetPackets(void) {}
void netBroadcastTaunt(int, int) {}
void CalcGameChecksum(void) {}
void netBroadcastPlayerLogoff(int) {}
void netBroadcastMyLogoff(bool) {}
void netInitialize(bool) { netResetToSinglePlayer(); }
void netBroadcastPlayerInfo(int) {}
void netCheckSync(void) {}
void netMasterUpdate(void) {}
void netGetInput(void) {}
void netPlayerQuit(int) {}
void netUpdate(void) {}
void netDeinitialize(void) {}
void netBroadcastNewGame(void) {}

// The renderer calls this while processing large draw loops.  In the PSP
// MVP network play is disabled, so there is no network tick to service.
extern "C" void faketimerhandler(void) {}
