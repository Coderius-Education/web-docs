import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import styles from './styles.module.css';

type CourseCard = {
  title: string;
  description: string;
  to: string;
  label: string;
};

const courses: CourseCard[] = [
  {
    title: 'HTML & CSS',
    description:
      'Leer de bouwstenen van het web. Van paginastructuur en tekst tot afbeeldingen, stijlen en flexbox.',
    to: '/docs/html-css/intro-html',
    label: 'Start HTML & CSS',
  },
  {
    title: 'JavaScript',
    description:
      'Maak je pagina interactief. Van knoppen en functies tot variabelen en events.',
    to: '/docs/js-basics/inline-onclick',
    label: 'Start JavaScript',
  },
];

function CourseCardItem({title, description, to, label}: CourseCard): ReactNode {
  return (
    <div className={styles.card}>
      <h3>{title}</h3>
      <p>{description}</p>
      <Link className="button button--primary" to={to}>
        {label}
      </Link>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.cardRow}>
          {courses.map((card) => (
            <CourseCardItem key={card.title} {...card} />
          ))}
        </div>
      </div>
    </section>
  );
}
