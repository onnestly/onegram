package org.onegram;

import java.util.regex.*;

public final class ReleaseVersion {
    private static final Pattern VERSION=Pattern.compile("(?i)\\bOneGram(?:[-_ ]+(?:Android|Windows|arm64|x64))*[-_ :]*v?(\\d{1,4}\\.\\d{1,4}\\.\\d{1,4})\\b");
    public static String find(String text){Matcher matcher=VERSION.matcher(text==null?"":text);return matcher.find()?matcher.group(1):null;}
    public static int compare(String a,String b){String[] x=a.split("\\."),y=b.split("\\.");if(x.length!=3||y.length!=3)throw new IllegalArgumentException();for(int i=0;i<3;i++){int compared=Integer.compare(Integer.parseInt(x[i]),Integer.parseInt(y[i]));if(compared!=0)return compared;}return 0;}
}
