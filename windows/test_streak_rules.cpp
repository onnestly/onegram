#include "../desktop/Telegram/SourceFiles/data/components/onegram_streak_rules.h"

extern "C" int main() {
	auto todayMask = 0;
	const auto lookup = [&](long long day) {
		if (day == 20000) return todayMask;
		if (day == 19999 || day == 19998) return 3;
		if (day == 19997) return 1;
		return 0;
	};
	using Data::OneGram::CountStreak;
	using Data::OneGram::Palette;
	if (CountStreak(lookup, 20000, 19995, false) != 2) return 1;
	todayMask = 1;
	if (CountStreak(lookup, 20000, 19995, false) != 2) return 2;
	todayMask = 3;
	if (CountStreak(lookup, 20000, 19995, false) != 3) return 3;
	if (CountStreak(lookup, 20000, 19998, false) != -1) return 4;
	if (CountStreak(lookup, 20002, 19995, false) != 0) return 5;
	if (CountStreak([](long long) { return 0; }, 20000, 0, true)) return 6;
	if (Palette(3).body != 0xfff8a01b) return 7;
	if (Palette(10).body != 0xfff7851c) return 8;
	if (Palette(30).body != 0xfff74f52) return 9;
	if (Palette(100).body != 0xffea20e0) return 10;
	if (Palette(200).body != 0xffb764f4) return 11;
	if (Palette(2, true).body != 0xfff8a01b) return 12;
	if (Palette(150, false).body != 0xffaaaaaa) return 13;
	if (CountStreak([](long long day) {
		return day <= 20000 && day > 19850 ? 3 : 0;
	}, 20000, 19849, false) != 150) return 14;
	return 0;
}
