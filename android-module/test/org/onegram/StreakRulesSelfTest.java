package org.onegram;
import org.onegram.streak.StreakRules;
import java.time.*;
import java.util.*;
public final class StreakRulesSelfTest {
    public static void main(String[] args){
        Map<Long,Integer> days=new HashMap<>();long today=20000;
        days.put(today-1,3);days.put(today-2,3);days.put(today-3,1);
        check(StreakRules.count(days,today,today-5,false)==2,"yesterday streak");
        days.put(today,1);check(StreakRules.count(days,today,today-5,false)==2,"one-sided today retains yesterday");
        days.put(today,3);check(StreakRules.count(days,today,today-5,false)==3,"both today increments");
        check(StreakRules.count(days,today,today-2,false)==-1,"unloaded history is not a real gap");
        check(StreakRules.count(days,today+2,today-5,false)==0,"missed day expires streak");
        check(StreakRules.count(new HashMap<>(),today,Long.MIN_VALUE,true)==0,"empty history");
        long moment=Instant.parse("2026-11-02T22:00:00Z").getEpochSecond();
        check(StreakRules.day(moment,ZoneId.of("Europe/Moscow"))==LocalDate.of(2026,11,3).toEpochDay(),"timezone midnight");
        check(StreakRules.colors(3)[2]==0xfff8a01b&&StreakRules.colors(10)[2]==0xfff7851c&&StreakRules.colors(30)[2]==0xfff74f52&&StreakRules.colors(100)[2]==0xffea20e0&&StreakRules.colors(200)[2]==0xffb764f4,"palette thresholds");
        check(StreakRules.colors(2,true)[2]==0xfff8a01b,"active two-day streak is yellow");
        check(StreakRules.colors(150,false)[2]==0xffaaaaaa,"today incomplete is gray at any length");
        Map<Long,Integer> history=new HashMap<>();for(int i=0;i<150;i++)history.put(today-i,3);
        check(StreakRules.count(history,today,today-151,false)==150,"five-month history included");
        check(StreakRules.count(history,today,today-50,false)==-1,"partial page cannot report a shorter streak");
        System.out.println("Streak rules: mutual participation, grace day, expiry, missing coverage, timezone and five palette bands passed");
    }
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
}
