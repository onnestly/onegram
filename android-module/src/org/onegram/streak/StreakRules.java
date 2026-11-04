package org.onegram.streak;

import java.time.*;
import java.util.*;

public final class StreakRules {
    public static long day(long seconds, ZoneId zone) {
        return Instant.ofEpochSecond(seconds).atZone(zone).toLocalDate().toEpochDay();
    }
    public static int count(Map<Long,Integer> days, long today, long coveredSince, boolean exhausted) {
        long cursor = today;
        if (days.getOrDefault(cursor, 0) != 3) cursor--;
        int count = 0;
        for (;;) {
            if (days.getOrDefault(cursor, 0) == 3) { count++; cursor--; continue; }
            return exhausted || cursor >= coveredSince ? count : -1;
        }
    }
    public static int[] colors(int count) {
        return colors(count,true);
    }
    public static int[] colors(int count,boolean activeToday) {
        if(!activeToday)return new int[]{0xffdddddd,0xffcccccc,0xffaaaaaa,0xff888888};
        if (count >= 200) return new int[]{0xffe5acef,0xffe788fa,0xffb764f4,0xffa14cf2};
        if (count >= 100) return new int[]{0xfffc70f0,0xffef98d4,0xffea20e0,0xff98498b};
        if (count >= 30) return new int[]{0xfffcc48c,0xfff4a67e,0xfff74f52,0xffde6b8b};
        if (count >= 10) return new int[]{0xfffadc6e,0xfff5be35,0xfff7851c,0xffda431b};
        if (count >= 1) return new int[]{0xfffbe33b,0xfff7ca2c,0xfff8a01b,0xffe87b23};
        return new int[]{0xffdddddd,0xffcccccc,0xffaaaaaa,0xff888888};
    }
}
