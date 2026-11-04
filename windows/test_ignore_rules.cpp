#include "../desktop/Telegram/SourceFiles/data/components/onegram_ignore_rules.h"
extern "C" int main() {
 using namespace Data::OneGram;
 constexpr auto state=BeginIgnore({},100,1000);
 if(state.hides(100,1000)||!state.hides(101,1000)||!state.blocksRead()||!state.blocksSend())return 1;
 constexpr auto preview=state.preview();
 if(preview.hides(101,1000)||!preview.blocksRead()||!preview.blocksSend())return 2;
 constexpr auto cancelled=preview.cancel();
 if(!cancelled.hides(101,1000)||!cancelled.hides(200,2000)||cancelled.boundaryId!=100)return 3;
 constexpr auto confirmed=preview.confirm();
 if(confirmed.blocksRead()||confirmed.blocksSend()||confirmed.hides(101,1000))return 4;
 constexpr auto repeated=BeginIgnore(cancelled,200,2000);
 if(repeated.boundaryId!=100||repeated.since!=1000)return 5;
 constexpr auto empty=BeginIgnore({},0,1000);
 if(empty.hides(0,999)||!empty.hides(0,1000))return 6;
 return 0;
}
