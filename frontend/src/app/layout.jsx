import './globals.css';

export const metadata = {
  title: 'CivicIQ | Your civic intelligence buddy',
  description: 'CivicIQ - Your civic intelligence buddy for Edison Township Engineering services.',
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
