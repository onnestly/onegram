package org.onegram;
public final class BrandingLabelsSelfTest {
    public static void main(String[] args){
        String value="Telegram: Telegram Premium, OneGram Premium, Звёзды Telegram и Звёзды OneGram";
        String expected="OneGram: Telegram Premium, Telegram Premium, Звёзды Telegram и Звёзды Telegram";
        if(!BrandingLabels.plain(value).equals(expected))throw new AssertionError(BrandingLabels.plain(value));
        if(!BrandingLabels.plain("Добро пожаловать в Телеграм").equals("Добро пожаловать в OneGram"))throw new AssertionError("App name");
        System.out.println("App branding and official Telegram service names verified");
    }
}
