#pragma once

namespace Data::OneGram {

template <typename Lookup>
int CountStreak(
		Lookup lookup,
		long long today,
		long long coveredSince,
		bool exhausted) {
	auto cursor = today;
	if (lookup(cursor) != 3) {
		--cursor;
	}
	auto count = 0;
	while (lookup(cursor) == 3) {
		++count;
		--cursor;
	}
	return (exhausted || cursor >= coveredSince) ? count : -1;
}

struct StreakPalette {
	unsigned int light;
	unsigned int warm;
	unsigned int body;
	unsigned int tip;
};

constexpr StreakPalette Palette(int count, bool activeToday = true) {
	if (!activeToday) {
		return { 0xffdddddd, 0xffcccccc, 0xffaaaaaa, 0xff888888 };
	}
	if (count >= 200) {
		return { 0xffe5acef, 0xffe788fa, 0xffb764f4, 0xffa14cf2 };
	} else if (count >= 100) {
		return { 0xfffc70f0, 0xffef98d4, 0xffea20e0, 0xff98498b };
	} else if (count >= 30) {
		return { 0xfffcc48c, 0xfff4a67e, 0xfff74f52, 0xffde6b8b };
	} else if (count >= 10) {
		return { 0xfffadc6e, 0xfff5be35, 0xfff7851c, 0xffda431b };
	} else if (count >= 1) {
		return { 0xfffbe33b, 0xfff7ca2c, 0xfff8a01b, 0xffe87b23 };
	}
	return { 0xffdddddd, 0xffcccccc, 0xffaaaaaa, 0xff888888 };
}

}  
