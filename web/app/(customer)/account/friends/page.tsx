'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';

import { useLocale } from '../../../../components/locale-provider';
import {
  disableCustomerFriendLink,
  getCustomerFriendLink,
  joinFriendByCode,
  listCustomerFriends,
  removeCustomerFriend,
  resetCustomerFriendLink,
  type CustomerFriend,
  type CustomerFriendLink,
} from '../../../../lib/customer-friends';

const AUTH_ERRORS = new Set(['invalid_or_expired_token', 'unauthorized', 'account_not_found', 'claim_inactive']);
const LOGIN_NEXT_PATH = '/auth/login?next=/account/friends';

function loginNextPath(joinCode: string): string {
  if (!joinCode) {
    return LOGIN_NEXT_PATH;
  }
  const next = `/account/friends?join=${encodeURIComponent(joinCode)}`;
  return `/auth/login?next=${encodeURIComponent(next)}`;
}

function CustomerFriendsPageContent() {
  const { replace } = useRouter();
  const searchParams = useSearchParams();
  const { messages } = useLocale();
  const copy = messages.customerPages.friends;
  const joinCode = searchParams.get('join')?.trim() ?? '';
  const [friendLink, setFriendLink] = useState<CustomerFriendLink | null>(null);
  const [friends, setFriends] = useState<CustomerFriend[]>([]);
  const [linkRequiresChannel, setLinkRequiresChannel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const requestIdRef = useRef(0);
  const joinAttemptedRef = useRef<string | null>(null);
  const authRedirectedRef = useRef(false);
  const preserveActionErrorRef = useRef(false);

  const loadData = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    if (preserveActionErrorRef.current) {
      preserveActionErrorRef.current = false;
    } else {
      setError('');
    }

    try {
      const [linkRes, friendsRes] = await Promise.all([
        getCustomerFriendLink(),
        listCustomerFriends(),
      ]);
      if (requestId !== requestIdRef.current) {
        return false;
      }
      if (!linkRes.ok) {
        if (AUTH_ERRORS.has(linkRes.error)) {
          authRedirectedRef.current = true;
          replace(loginNextPath(joinCode));
          return false;
        }
        if (linkRes.error === 'owner_channel_required') {
          setFriendLink(null);
          setLinkRequiresChannel(true);
        } else {
          setError(copy.loadFailure);
          return false;
        }
      } else {
        setFriendLink(linkRes.data);
        setLinkRequiresChannel(false);
      }
      if (!friendsRes.ok) {
        if (AUTH_ERRORS.has(friendsRes.error)) {
          authRedirectedRef.current = true;
          replace(loginNextPath(joinCode));
          return false;
        }
        setError(copy.loadFailure);
        return false;
      }
      setFriends(friendsRes.data);
      return true;
    } catch {
      if (requestId === requestIdRef.current) {
        setError(copy.loadFailure);
      }
      return false;
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [copy.loadFailure, joinCode, replace]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const runJoinByCode = useCallback(
    async (code: string) => {
      let redirectedToAuth = false;
      setActionPending(true);
      setError('');
      setNotice('');
      try {
        const res = await joinFriendByCode(code);
        if (!res.ok) {
          if (AUTH_ERRORS.has(res.error)) {
            redirectedToAuth = true;
            authRedirectedRef.current = true;
            replace(loginNextPath(code));
            return;
          }
          preserveActionErrorRef.current = true;
          setError(res.error === 'self_friendship_forbidden' ? copy.inviteSelf : copy.actionFailure);
          return;
        }
        if (res.data.status === 'deferred_channel_required') {
          setNotice(copy.inviteNeedsChannel);
          return;
        }
        setNotice(copy.inviteSent);
        await loadData();
      } catch {
        setError(copy.actionFailure);
      } finally {
        setActionPending(false);
        if (!redirectedToAuth && !authRedirectedRef.current) {
          replace('/account/friends');
        }
      }
    },
    [copy.actionFailure, copy.inviteNeedsChannel, copy.inviteSelf, copy.inviteSent, loadData, replace],
  );

  useEffect(() => {
    if (loading || !joinCode || authRedirectedRef.current || joinAttemptedRef.current === joinCode) {
      return;
    }
    joinAttemptedRef.current = joinCode;
    void runJoinByCode(joinCode);
  }, [joinCode, loading, runJoinByCode]);

  async function copyLink() {
    if (!friendLink) {
      return;
    }
    setError('');
    setNotice('');
    try {
      await navigator.clipboard.writeText(friendLink.url);
      setNotice(copy.copied);
    } catch {
      setError(copy.actionFailure);
    }
  }

  async function resetLink() {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await resetCustomerFriendLink();
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(joinCode));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  async function disableLink() {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await disableCustomerFriendLink();
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(joinCode));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      setFriendLink(null);
      setNotice(copy.linkDisabled);
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  async function removeFriend(friendAccountId: string) {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await removeCustomerFriend(friendAccountId);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(joinCode));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  return (
    <section className="customer-view customer-view--wide customer-friends-page">
      <div className="customer-panel customer-panel--wide customer-friends-panel">
        <div className="customer-panel__head">
          <p className="customer-panel__eyebrow">{copy.eyebrow}</p>
          <h1 className="customer-panel__title">{copy.title}</h1>
          <p className="customer-panel__body">{copy.description}</p>
        </div>

        {loading ? <p className="customer-inline-note">{copy.loading}</p> : null}
        {error ? <p className="customer-inline-note customer-inline-note--error">{error}</p> : null}
        {notice ? <p className="customer-inline-note">{notice}</p> : null}

        <section className="customer-friends-section" aria-labelledby="friend-link-title">
          <div>
            <h2 id="friend-link-title">{copy.linkTitle}</h2>
            <p>{copy.linkDescription}</p>
          </div>
          <div className="customer-friend-link-box">
            <span>{friendLink?.url ?? ''}</span>
          </div>
          {linkRequiresChannel && !friendLink ? (
            <p className="customer-inline-note">{copy.linkRequiresChannel}</p>
          ) : null}
          <div className="customer-action-row">
            <button
              type="button"
              className="customer-action customer-action--primary"
              onClick={copyLink}
              disabled={!friendLink || actionPending}
            >
              {copy.copyLink}
            </button>
            <button
              type="button"
              className="customer-action customer-action--secondary"
              onClick={resetLink}
              disabled={!friendLink || actionPending}
            >
              {copy.resetLink}
            </button>
            <button
              type="button"
              className="customer-action customer-action--secondary"
              onClick={disableLink}
              disabled={!friendLink || actionPending}
            >
              {copy.disableLink}
            </button>
          </div>
        </section>

        <section className="customer-friends-section" aria-labelledby="current-friends-title">
          <h2 id="current-friends-title">{copy.friendsTitle}</h2>
          {friends.length === 0 ? (
            <p className="customer-friends-empty">{copy.emptyFriends}</p>
          ) : (
            <div className="customer-friends-list">
              {friends.map((friend) => (
                <article className="customer-friend-row" key={friend.id}>
                  <div>
                    <strong>{friend.counterpartProfile?.displayName || copy.unknownFriend}</strong>
                    <span>{friend.counterpartAccountId}</span>
                  </div>
                  <div className="customer-friend-row__actions">
                    <button
                      type="button"
                      className="customer-action customer-action--secondary"
                      onClick={() => void removeFriend(friend.counterpartAccountId)}
                      disabled={actionPending}
                    >
                      {copy.removeFriend}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

export default function CustomerFriendsPage() {
  return (
    <Suspense fallback={null}>
      <CustomerFriendsPageContent />
    </Suspense>
  );
}
