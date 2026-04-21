## Summary

- align `/channels/wechat-personal` with the branded customer auth/setup visual language
- keep the existing channel state machine, API calls, and action behavior unchanged

## Surfaces

- `gateway-web`

## Plan

- add focused page tests for the branded layout structure
- refactor the page into branded panels using the existing public-site visual tokens
- run targeted gateway web tests for the channel page

## Verification

- `pnpm --dir gateway/packages/web test -- app/'(customer)'/channels/wechat-personal/page.test.tsx`
