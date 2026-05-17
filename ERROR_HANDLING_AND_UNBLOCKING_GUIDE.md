# Error Handling & YouTube Unblocking Configuration Guide

## Overview
This guide explains the new error handling system and advanced YouTube unblocking strategies implemented in ThugTools.

---

## 📧 Email Error Notifications

### Purpose
Real errors are now hidden from users (they see generic messages) and sent to your email instead for debugging.

### Configuration (Railway Environment Variables)

Add these variables in your Railway project settings:

```
ENABLE_EMAIL_ALERTS=1
ADMIN_EMAIL=your-email@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### SMTP Setup Examples

**Gmail:**
- SMTP_SERVER: `smtp.gmail.com`
- SMTP_PORT: `587`
- SMTP_USER: Your Gmail address
- SMTP_PASSWORD: App Password (generate at https://myaccount.google.com/apppasswords)

**Outlook:**
- SMTP_SERVER: `smtp-mail.outlook.com`
- SMTP_PORT: `587`
- SMTP_USER: Your Outlook email
- SMTP_PASSWORD: Your Outlook password

**Custom SMTP:**
- Use your provider's SMTP server details

### What You'll Receive
- Error type (ApiError, DownloadError, HTTP Error, Unexpected Error)
- Full error message
- Stack trace (for unexpected errors)
- Request information (path, method, IP, URL)
- Timestamp

---

## 🚀 Advanced YouTube Unblocking Strategies

The YouTube downloader now uses multiple layers of protection against blocking:

### 1. User Agent Rotation
- 11 different user agents (Chrome, Firefox, Safari on Windows, Mac, Linux, iOS, Android)
- Randomly selected for each request
- Mimics real browser traffic

### 2. Random Headers Generation
- Varying Accept headers
- Multiple language options (en-US, en-GB, en-IN with Hindi)
- Random DNT, Cache-Control, Sec-Fetch headers
- Makes each request look different

### 3. Proxy Rotation
Configure multiple proxies for rotation:

```
PROXY_LIST=http://proxy1.example.com:8080,http://proxy2.example.com:8080,socks5://proxy3.example.com:1080
```

Or single proxy:
```
YOUTUBE_PROXY=http://your-proxy.com:8080
```

### 4. Circuit Breaker Pattern
- Failed instances are temporarily blacklisted (5 min cooldown)
- Prevents repeated attempts on dead endpoints
- Automatically retries after cooldown period

### 5. Massive Instance Pools

**Invidious Instances (45+ static + dynamic discovery):**
- Increased from 12 to 45+ static instances
- Dynamic discovery from api.invidious.io
- Shuffled for randomization
- Increased cache limit from 40 to 60 instances
- Lowered health threshold (0.4 → 0.3) for more options

**Piped Instances (28+ static + dynamic discovery):**
- Increased from 6 to 28+ static instances  
- Dynamic discovery from piped-instances.kavin.rocks
- Shuffled for randomization
- Increased cache limit from 30 to 50 instances

### 6. Enhanced Cobalt API
- Multiple self-hosted Cobalt relay instances with fallback
- No public Cobalt API is assumed by default; deploy your own relay from `cobalt-relay/`
- Configure relay instances:
  ```
  YOUTUBE_FORCE_COOKIELESS=1
  COBALT_API_URL=https://your-cobalt-relay.example/
  COBALT_API_URLS=https://relay1.example/,https://relay2.example/
  ```
- Random instance selection
- Failed relay cooldown before retrying it again
- Best-quality resolver scoring instead of first-response-wins
- Fresh preview-session stream reuse before a second YouTube extraction
- Proxy support
- Random headers

### 7. Increased Parallel Execution
- Workers increased from 16 to 32
- Instance limit increased from 30 to 50
- Timeout increased from 45 to 60 seconds
- Faster fallback between instances

### 8. Random Delays
- 0.1-0.8 second random delays between requests
- Avoids rate limiting detection
- Mimics human behavior

---

## 🔧 Complete Configuration Example

Add these to your Railway environment variables:

```bash
# Email Alerts
ENABLE_EMAIL_ALERTS=1
ADMIN_EMAIL=your-email@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Proxy Rotation (Optional but Recommended)
PROXY_LIST=http://proxy1.com:8080,http://proxy2.com:8080,socks5://proxy3.com:1080

# Single Proxy Alternative
YOUTUBE_PROXY=http://your-proxy.com:8080

# Self-hosted Cobalt relay instances (Optional)
YOUTUBE_FORCE_COOKIELESS=1
COBALT_API_URL=https://your-cobalt-relay.example/
COBALT_API_URLS=https://relay1.example/,https://relay2.example/

# Additional Invidious/Piped Instances (Optional)
INVIDIOUS_API_URLS=https://custom-invidious1.com,https://custom-invidious2.com
PIPED_API_URLS=https://custom-piped1.com,https://custom-piped2.com
```

---

## 🛡️ Why This Makes YouTube Blocking Difficult

1. **Distributed Traffic:** Requests spread across 100+ instances
2. **Randomization:** Every request looks different (UA, headers, timing)
3. **Proxy Support:** Can route through different IPs
4. **Circuit Breaker:** Automatically avoids dead endpoints
5. **Multiple APIs:** Invidious, Piped, Cobalt, oEmbed fallbacks
6. **Parallel Execution:** Tries 50 instances simultaneously
7. **No Single Point of Failure:** If one API fails, others continue

YouTube would need to:
- Block 100+ different domains
- Detect and block 11 different user agents
- Identify and block random header patterns
- Block multiple proxy services
- Block multiple API services simultaneously

This is extremely difficult and costly for YouTube to maintain.

---

## 📊 Error Messages Shown to Users

Users now see generic, friendly messages:
- "Something went wrong. Server is having a problem. Please try again after some time."
- "File is too large. Max upload size is 250 MB."
- Simplified download errors (no technical details)

Real errors with full details are sent to your email for debugging.

---

## 🔄 How to Test

1. Deploy with new configuration
2. Try downloading a YouTube video
3. Check your email for any error notifications
4. Monitor Railway logs for email sending status
5. Test with different videos to verify unblocking works

---

## 🚨 Important Notes

- **Email alerts are optional** - Set ENABLE_EMAIL_ALERTS=0 to disable
- **Proxies are optional** - System works without them, but they add protection
- **Custom instances are optional** - Built-in instances work well
- **No cookies required** - System works without YouTube cookies
- **Automatic fallback** - If one method fails, others are tried automatically

---

## 📞 Support

If you still experience YouTube blocking:
1. Check your email for error details
2. Add more proxies to PROXY_LIST
3. Add custom Cobalt instances
4. Deploy to a different Railway region
5. Consider using residential proxies for maximum protection

---

## 🔒 Security Best Practices

- Use app passwords for Gmail (not your main password)
- Keep SMTP credentials secure
- Use HTTPS proxies only
- Rotate proxies periodically
- Monitor email alerts for unusual activity
