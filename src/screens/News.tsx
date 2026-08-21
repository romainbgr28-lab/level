import { useState } from 'react';
import Header from '../components/Header';
import { newsItems } from '../data/mockData';

export default function News() {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="screen">
      <Header title="Actu" />
      <h1 className="page-title">Actu du jour</h1>
      {newsItems.map((item) => {
        const isOpen = openId === item.id;
        return (
          <div className="accordion" key={item.id}>
            <button
              className="accordion__head"
              onClick={() => setOpenId(isOpen ? null : item.id)}
              aria-expanded={isOpen}
            >
              <span className="tag">{item.tag}</span>
              <span style={{ fontSize: 16, fontWeight: 600 }}>{item.title}</span>
              <span className="accordion__summary">{item.summary}</span>
            </button>
            {isOpen && <div className="accordion__body">{item.content}</div>}
          </div>
        );
      })}
    </div>
  );
}
