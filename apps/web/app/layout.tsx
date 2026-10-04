import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'BrowserGrid · Browser testing infrastructure',description:'Isolated browser tests, live execution logs, and artifacts. Self-hosted.'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
