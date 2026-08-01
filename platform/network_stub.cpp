// Single-player network stub for the PSP MVP.
#include "network.h"

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

void netResetState(void) {}
void netResetToSinglePlayer(void) { gNetMode = NETWORK_NONE; gInitialNetPlayers = 1; }
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
