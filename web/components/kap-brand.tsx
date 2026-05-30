import { cn } from '../lib/utils';

const KAP_KOALA_BADGE_SRC = '/kap-koala-badge.png';
const KAP_KOALA_HERO_SRC = '/kap-koala-hero.png';

export function KapKoalaBadge({
  className,
  alt = 'Kap koala badge',
}: {
  className?: string;
  alt?: string;
}) {
  return (
    <img
      src={KAP_KOALA_BADGE_SRC}
      alt={alt}
      width={1254}
      height={1254}
      className={cn('kap-koala-badge', className)}
    />
  );
}

export function KapKoalaHero({
  className,
  alt = 'Kap koala mascot',
}: {
  className?: string;
  alt?: string;
}) {
  return (
    <img
      src={KAP_KOALA_HERO_SRC}
      alt={alt}
      width={1183}
      height={1330}
      className={cn('kap-koala-hero', className)}
    />
  );
}
