import './globals.css';

export const metadata = {
  title: 'Pixelvyne Smart Assistant | City of Pixelvyne Citizen Portal',
  description: 'Official municipal procedural web assistant with deterministic flowcharts, grounded link RAG, and official government PDF delivery.',
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
