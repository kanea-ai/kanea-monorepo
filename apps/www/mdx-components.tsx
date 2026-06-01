import type { MDXComponents } from 'mdx/types';
import { mdxComponents } from './components/docs/mdx-components';

// Next.js looks for this file at the project root to wire MDX rendering
// to our shared component mapping. App Router convention.
export function useMDXComponents(components: MDXComponents): MDXComponents {
  return { ...components, ...mdxComponents };
}
