<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>
    <#if section = "header">
        Вход в систему
    <#elseif section = "form">
        <#if realm.password>
            <form id="kc-form-login" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post" class="neon-form">
                <#if !usernameHidden??>
                    <div class="form-group">
                        <label for="username" class="form-label">
                            <#if !realm.loginWithEmailAllowed>
                                ${msg("username")}
                            <#elseif !realm.registrationEmailAsUsername>
                                ${msg("usernameOrEmail")}
                            <#else>
                                ${msg("email")}
                            </#if>
                        </label>
                        <div class="input-wrapper">
                            <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                                <circle cx="12" cy="7" r="4"></circle>
                            </svg>
                            <input tabindex="1" id="username" class="neon-input with-icon" name="username" value="${(login.username!'')}" type="text" autofocus autocomplete="username" placeholder="Логин или email"
                                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>" />
                        </div>
                    </div>
                </#if>

                <div class="form-group">
                    <div class="label-row">
                        <label for="password" class="form-label">${msg("password")}</label>
                        <#if realm.resetPasswordAllowed>
                            <a tabindex="5" href="${url.loginResetCredentialsUrl}" class="link-muted">${msg("doForgotPassword")}</a>
                        </#if>
                    </div>
                    <div class="input-wrapper">
                        <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                        </svg>
                        <input tabindex="2" id="password" class="neon-input with-icon with-eye" name="password" type="password" autocomplete="current-password" placeholder="••••••••"
                               aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>" />
                        <button type="button" id="togglePasswordBtn" class="toggle-password" title="Показать пароль" tabindex="-1">
                            <svg class="eye-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                            <svg class="eye-closed" style="display:none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                                <line x1="1" y1="1" x2="23" y2="23"></line>
                            </svg>
                        </button>
                    </div>
                </div>

                <#if messagesPerField.existsError('username','password')>
                    <div class="alert alert-error">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="8" x2="12" y2="12"></line>
                            <line x1="12" y1="16" x2="12.01" y2="16"></line>
                        </svg>
                        <#assign fieldError = messagesPerField.getFirstError('username','password')>
                        <#if fieldError?contains("Invalid username or password") || fieldError?contains("Неверные имя пользователя или пароль")>
                            <span>Неверный логин или пароль</span>
                        <#else>
                            <span>${kcSanitize(fieldError)?no_esc}</span>
                        </#if>
                    </div>
                </#if>

                <#if realm.rememberMe && !usernameHidden??>
                    <div class="form-group remember-group">
                        <label class="checkbox-label" for="rememberMe">
                            <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>>
                            <span class="custom-checkbox"></span>
                            <span>${msg("rememberMe")}</span>
                        </label>
                    </div>
                </#if>

                <div class="form-actions">
                    <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                    <button tabindex="4" class="btn btn-primary btn-full neon-btn" name="login" id="kc-login" type="submit">
                        <span>Войти</span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18">
                            <line x1="5" y1="12" x2="19" y2="12"></line>
                            <polyline points="12 5 19 12 12 19"></polyline>
                        </svg>
                    </button>
                </div>
            </form>

            <script>
                // Password visibility toggle
                const toggleBtn = document.getElementById('togglePasswordBtn');
                const passwordInput = document.getElementById('password');
                if (toggleBtn && passwordInput) {
                    toggleBtn.addEventListener('click', function() {
                        const isPassword = passwordInput.getAttribute('type') === 'password';
                        passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
                        const eyeOpen = toggleBtn.querySelector('.eye-open');
                        const eyeClosed = toggleBtn.querySelector('.eye-closed');
                        if (isPassword) {
                            eyeOpen.style.display = 'none';
                            eyeClosed.style.display = 'block';
                        } else {
                            eyeOpen.style.display = 'block';
                            eyeClosed.style.display = 'none';
                        }
                    });
                }
            </script>
        </#if>

        <#if realm.password && social.providers??>
            <div class="social-login-separator">
                <span>или войти через</span>
            </div>
            <div class="social-providers">
                <#list social.providers as p>
                    <a id="social-${p.alias}" class="btn btn-secondary social-btn" href="${p.loginUrl}">
                        <span>${p.displayName!}</span>
                    </a>
                </#list>
            </div>
        </#if>
    <#elseif section = "info" >
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div class="registration-hint">
                <span>${msg("noAccount")}</span>
                <a tabindex="6" href="${url.registrationUrl}" class="link-accent">${msg("doRegister")}</a>
            </div>
        </#if>
    </#if>
</@layout.registrationLayout>
