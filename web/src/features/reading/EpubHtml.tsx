export type EpubDocument = {
  href: string;
  html: string;
};

export function EpubHtml({ documents }: { documents: EpubDocument[] }) {
  return (
    <div className="reading-epub mx-auto max-w-[40rem]">
      {documents.map((doc) => (
        <section key={doc.href} dangerouslySetInnerHTML={{ __html: doc.html }} />
      ))}
    </div>
  );
}
