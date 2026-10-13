import { NavLink } from 'react-router-dom';
export default function ResearchFeedTabs() {
  return <nav aria-label="Research feeds" className="flex gap-6 border-b pb-3 mb-6">
    <NavLink to="/" end className={({ isActive }) => isActive ? 'font-semibold underline' : ''}>Discover</NavLink>
    <NavLink to="/following" className={({ isActive }) => isActive ? 'font-semibold underline' : ''}>Following</NavLink>
  </nav>;
}
