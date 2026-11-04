import './globals.css';

export const metadata = {
  title: 'CivicIQ | Mushkil Your Edison Township Buddy',
  description: 'CivicIQ - Mushkil Your Edison Township Buddy for Edison Township, New Jersey.',
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
