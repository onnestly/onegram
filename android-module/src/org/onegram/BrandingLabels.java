package org.onegram;

import java.util.*;
import java.util.regex.*;

public final class BrandingLabels {
    private static final String BRAND="(?:Telegram|OneGram|Телеграм(?:м)?(?:е|а|у|ом)?)";
    private static final String PRODUCT="(?:Premium|Stars|Business|Passport|Gateway|Wallet|Gifts)";
    private static final String LOCAL="(?:Зв[её]зд[а-яё]*|Премиум|Подар[а-яё]*|Бизнес[а-яё]*)";
    private static final Pattern SERVICES=Pattern.compile(BRAND+"\\s+"+PRODUCT+"\\b|(?:"+PRODUCT+"|"+LOCAL+")\\s+"+BRAND,Pattern.CASE_INSENSITIVE|Pattern.UNICODE_CASE);
    public static String plain(String input){
        List<String> saved=new ArrayList<>();Matcher matcher=SERVICES.matcher(input);StringBuffer text=new StringBuffer();
        while(matcher.find()){
            saved.add(matcher.group().replace("OneGram","Telegram").replace("ONEGRAM","TELEGRAM"));
            matcher.appendReplacement(text,Matcher.quoteReplacement("\ue000"+(saved.size()-1)+"\ue001"));
        }
        matcher.appendTail(text);
        String result=text.toString().replace("Telegram Desktop","OneGram").replace("Telegram","OneGram").replace("TELEGRAM","ONEGRAM")
            .replaceAll("(?iu)телеграм(?:м)?(?:е|а|у|ом)?(?=\\W|$)","OneGram");
        for(int i=0;i<saved.size();i++)result=result.replace("\ue000"+i+"\ue001",saved.get(i));
        return result;
    }
}
