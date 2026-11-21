'use strict';

/** Reads presenceview:// links and decides which pages the app may show. */

// Invite tokens are signed JWTs: three base64url parts joined by dots
const INVITE_TOKEN = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const MAX_TOKEN_LENGTH = 2000;

/** The invite token in presenceview://interview?invite=TOKEN, or null. */
function inviteFromLink(link) {
  let url;
  try {
    url = new URL(link);
  } catch {
    return null;
  }
  if (url.protocol !== 'presenceview:' || url.hostname !== 'interview') return null;
  const token = url.searchParams.get('invite');
  return token && token.length <= MAX_TOKEN_LENGTH && INVITE_TOKEN.test(token) ? token : null;
}

/** On Windows and Linux a link arrives as a command-line argument. */
function inviteFromArgv(argv) {
  for (const arg of argv) {
    if (arg.startsWith('presenceview://')) return inviteFromLink(arg);
  }
  return null;
}

function interviewUrl(appUrl, token) {
  const url = new URL('/interview', appUrl);
  if (token) url.searchParams.set('invite', token);
  return url.toString();
}

/** Same scheme, host and port as the configured app. */
function isAllowedUrl(target, appUrl) {
  try {
    return new URL(target).origin === new URL(appUrl).origin;
  } catch {
    return false;
  }
}

module.exports = { inviteFromLink, inviteFromArgv, interviewUrl, isAllowedUrl };
