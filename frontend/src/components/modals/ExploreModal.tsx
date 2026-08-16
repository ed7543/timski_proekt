import type { ExploreResponse } from '../../types/chat';
import { ModalShell } from './ModalShell';

function siteFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export function ExploreModal({ data, onClose }: { data: ExploreResponse; onClose: () => void }) {
  return (
    <ModalShell onClose={onClose}>
      <h2>Explore related topics</h2>
      <div className="modal-subtitle">{data.links.length} links found</div>

      {data.links.length === 0 ? (
        <div className="empty">No related links found.</div>
      ) : (
        data.links.map((l) => (
          <a
            key={l.url}
            className="src"
            href={l.url}
            target="_blank"
            rel="noreferrer"
            style={{ display: 'block', marginBottom: 8 }}
          >
            <div className="src-row">
              <div className="src-body">
                <div className="src-title">{l.title || l.url}</div>
                <div className="src-meta">
                  <span>{siteFromUrl(l.url)}</span>
                </div>
              </div>
            </div>
          </a>
        ))
      )}

      <div className="modal-footer">
        <div />
        <button className="modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
