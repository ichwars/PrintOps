import type { ProjectCreate } from '../api/client';

export type ProductionProjectDraft = Pick<ProjectCreate, 'name' | 'description' | 'target_parts_count' | 'parent_id'> & {
  productionArticleId?: number;
};

export type ProjectsLocationState = { productionDraft?: ProductionProjectDraft };
