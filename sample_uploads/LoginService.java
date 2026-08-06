package com.app.auth;

import com.app.model.User;

/**
 * Source file matching java_nullpointer.log.
 * Upload both together to see the log analysis and remediation agents agree
 * on the same failure point.
 */
public class LoginService {

    private final SessionStore sessionStore;

    public LoginService(SessionStore sessionStore) {
        this.sessionStore = sessionStore;
    }

    public boolean authenticate(String token) {
        return validate(token);
    }

    public boolean validate(String token) {
        // BUG: lookup returns null when the session has expired or was evicted
        // from the cache, and the result is dereferenced without a guard.
        User user = sessionStore.lookup(token);
        return user.getRole().isActive();
    }
}
