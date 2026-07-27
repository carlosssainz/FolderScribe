import type { ReactNode } from 'react';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { source } from '../../lib/source';

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      nav={{ title: 'FolderScribe' }}
      tree={source.pageTree}
    >
      {children}
    </DocsLayout>
  );
}
