 

#pragma once

#include "base/const_string.h"

#define TDESKTOP_REQUESTED_ALPHA_VERSION (0ULL)

#ifdef TDESKTOP_ALLOW_CLOSED_ALPHA
#define TDESKTOP_ALPHA_VERSION TDESKTOP_REQUESTED_ALPHA_VERSION
#else  
#define TDESKTOP_ALPHA_VERSION (0ULL)
#endif  

constexpr auto AppId = "{0002EB8A-368C-57F9-9CAB-821F6AA56452}"_cs;
constexpr auto AppNameOld = "OneGram"_cs;
constexpr auto AppName = "OneGram"_cs;
constexpr auto AppFile = "OneGramClient"_cs;
constexpr auto AppVersion = 7003004;
constexpr auto AppVersionStr = "7.3.4";
constexpr auto AppBetaVersion = true;
constexpr auto AppAlphaVersion = TDESKTOP_ALPHA_VERSION;
