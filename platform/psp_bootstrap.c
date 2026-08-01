#include <pspkernel.h>
#include <pspdebug.h>

PSP_MODULE_INFO("JFBlood PSP Bootstrap", PSP_MODULE_USER, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);

int main(void)
{
    pspDebugScreenInit();
    pspDebugScreenPrintf("JFBlood PSP bootstrap\n");
    pspDebugScreenPrintf("PSPDEV + PSPSDK: OK\n");
    pspDebugScreenPrintf("Proximo passo: integrar JFBuild classico.\n");

    sceKernelSleepThread();
    return 0;
}
