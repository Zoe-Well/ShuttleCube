export type Problem = { type: string; title: string; status: number; detail: string; instance?: string; errors?: unknown[] };
export class ApiProblem extends Error { constructor(public readonly problem: Problem) { super(problem.detail); } }
