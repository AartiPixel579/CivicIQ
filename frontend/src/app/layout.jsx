import './globals.css';

export const metadata = {
  title: 'CivicIQ | Township of Edison Resident Services Assistant',
  description: 'Official municipal procedural assistant for the Township of Edison, New Jersey with deterministic service flowcharts, grounded document RAG, and official government PDF delivery.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-slate-100 text-slate-800">
        {children}
      </body>
    </html>
  );
}
