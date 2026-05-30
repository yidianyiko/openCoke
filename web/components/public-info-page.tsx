import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

import { CokePublicShell } from './coke-public-shell';

type PublicInfoSection = {
  title: string;
  body: string;
};

type PublicInfoPageProps = {
  eyebrow: string;
  title: string;
  lead: string;
  sections: ReadonlyArray<PublicInfoSection>;
  primaryLink: {
    href: string;
    label: string;
  };
  secondaryLink: {
    href: string;
    label: string;
  };
};

export function PublicInfoPage({
  eyebrow,
  title,
  lead,
  sections,
  primaryLink,
  secondaryLink,
}: PublicInfoPageProps) {
  return (
    <CokePublicShell>
      <section className="info-page">
        <div className="wrap">
          <div className="info-page__hero">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{lead}</p>
            <div className="info-page__actions">
              <Link href={primaryLink.href} className="btn-sticker">
                {primaryLink.label}
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link href={secondaryLink.href} className="btn-ghost">
                {secondaryLink.label}
              </Link>
            </div>
          </div>

          <div className="info-page__grid">
            {sections.map((section, index) => (
              <article key={section.title} className="info-page__card">
                <span className="info-page__index">{String(index + 1).padStart(2, '0')}</span>
                <h2>{section.title}</h2>
                <p>{section.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </CokePublicShell>
  );
}
