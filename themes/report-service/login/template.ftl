<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html lang="${(locale.currentLanguageTag)!'ru'}" data-theme="dark">

<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">

    <title>Вход в систему сервиса отчетов</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">

    <#if properties.stylesCommon?has_content>
        <#list properties.stylesCommon?split(' ') as style>
            <link href="${url.resourcesCommonPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.styles?has_content>
        <#list properties.styles?split(' ') as style>
            <link href="${url.resourcesPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.scripts?has_content>
        <#list properties.scripts?split(' ') as script>
            <script src="${url.resourcesPath}/${script}" type="text/javascript"></script>
        </#list>
    </#if>
</head>

<body>
    <!-- Background Atmosphere -->
    <div class="grid-bg"></div>
    <div class="glow-orb purple"></div>
    <div class="glow-orb blue"></div>

    <div class="login-wrapper">
        <div class="glass-panel login-card">
            <!-- Rostelecom Brand Header -->
            <div class="brand">
                <div class="brand-icon">
                    <svg viewBox="0 0 225 372" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="rtPurpleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#C084FC"/>
                                <stop offset="100%" stop-color="#7E22CE"/>
                            </linearGradient>
                            <linearGradient id="rtOrangeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#FB923C"/>
                                <stop offset="100%" stop-color="#EA580C"/>
                            </linearGradient>
                        </defs>
                        <path fill="url(#rtPurpleGrad)" d="m 7.496873,353.79 c -0.00594,-4.557 1.69999,-8.951 4.77999,-12.31 v 0 l 10.13,-10.11 c 4.82,-4.88 10,-10.1 17.63,-17.69 8.57,-8.54 20.2,-20.09 37.8,-37.58 l 0.05,-0.05 17.15,-17.07 0.35,-0.34 C 123.86696,230.32 164.38696,189.97 223.88696,130.72 L 93.226863,0 l -74,74.06 C -2.863127,96.16 0.136874,110.63 0.136874,140.33 v 203.19 c -2.36e-4,5.694 1.742649,11.253 4.994419,15.927 3.25177,4.675 7.85657,8.242 13.19557,10.223 v 0 c -3.1903,-1.254 -5.9293,-3.44 -7.8608,-6.272 -1.93152,-2.832 -2.9661,-6.18 -2.96919,-9.608 z"/>
                        <path fill="url(#rtOrangeGrad)" d="m 18.326863,369.67 c 0.22,0.09 0.44,0.19 0.67,0.27 0.23,0.08 0.43,0.13 0.73,0.2 2.6646,0.834 5.438,1.268 8.23,1.29 H 173.04696 l -95.150097,-95.4 -0.05,0.05 c -17.6,17.49 -29.23,29 -37.8,37.58 -7.61,7.59 -12.81,12.81 -17.63,17.69 l -10.13,10.11 c -3.08,3.359 -4.78596,7.752 -4.78001,12.31 -0.00171,3.43 1.02952,6.781 2.95941,9.617 1.9299,2.836 4.669,5.026 7.8606,6.283 z"/>
                    </svg>
                </div>
                <div class="brand-text">
                    <h1>Сервис<br>отчетов</h1>
                    <span class="brand-sub">Авторизация в системе</span>
                </div>
            </div>

            <!-- Page Title / Subtitle -->
            <div class="login-header">
                <h2><#nested "header"></h2>
            </div>

            <!-- Alerts / Messages -->
            <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                <div class="alert alert-${message.type}">
                    <#if message.type = 'success'>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                    <#elseif message.type = 'warning'>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    <#elseif message.type = 'error'>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    <#else>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                    </#if>
                    <#if message.summary?contains("Invalid username or password") || message.summary?contains("Неверные имя пользователя или пароль")>
                        <span>Неверный логин или пароль</span>
                    <#else>
                        <span>${kcSanitize(message.summary)?no_esc}</span>
                    </#if>
                </div>
            </#if>

            <!-- Form Content -->
            <div class="login-form-area">
                <#nested "form">
            </div>

            <!-- Optional Info / Registration / Links -->
            <#if displayInfo>
                <div class="login-info-area">
                    <#nested "info">
                </div>
            </#if>
        </div>
    </div>
</body>
</html>
</#macro>
