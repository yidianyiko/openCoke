'use client';

import Link from 'next/link';

import { useLocale } from '../../../components/locale-provider';

export default function CustomerChannelsPage() {
  const { locale, messages } = useLocale();
  const copy = messages.customerPages.channelsIndex;

  return (
    <section className="customer-view">
      <div className="customer-panel customer-panel--hero">
        <p className="customer-panel__eyebrow">{copy.eyebrow}</p>
        <h1 className="customer-panel__title">{copy.title}</h1>
        <p className="customer-panel__body">{copy.description}</p>
      </div>

      <div className="customer-link-grid">
        <Link href="/channels/wechat-personal" className="customer-link-card">
          <span className="customer-link-card__eyebrow">{locale === 'zh' ? '个人入口' : 'Personal entry'}</span>
          <h2>{copy.wechatPersonalTitle}</h2>
          <p>{copy.wechatPersonalDescription}</p>
          <span className="customer-link-card__cta">{locale === 'zh' ? '打开设置' : 'Open setup'}</span>
        </Link>
      </div>
    </section>
  );
}
