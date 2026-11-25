% SPDX-License-Identifier: MIT OR Apache-2.0
function out = release_linkage_reference(priorO, priorP, ambientN, ambientP, rounding, suppressBelow, effect)
%RELEASE_LINKAGE_REFERENCE Exact distinguishing advantage on a synthetic model.
%   An adversary sees the published before/after pair under every policy at
%   once and knows the prior, ambient model, and policies. Advantage is the
%   total variation distance. Occupancy after the interval is clamped at zero.
%   rounding and suppressBelow are equal-length vectors, one entry per policy.
%   Not executed in MATLAB or Octave by its author.
if nargin < 7, effect = 1; end
priorO = priorO(:);
priorP = priorP(:);
ambientN = ambientN(:);
ambientP = ambientP(:);
rounding = rounding(:).';
suppressBelow = suppressBelow(:).';
assert(numel(priorO) == numel(priorP) && all(priorO >= 0) && all(priorO == round(priorO)) ...
    && all(priorP >= 0) && abs(sum(priorP) - 1) < 1e-9, 'prior');
assert(numel(ambientN) == numel(ambientP) && all(ambientN == round(ambientN)) ...
    && all(ambientP >= 0), 'ambient');
assert(numel(rounding) == numel(suppressBelow) && all(rounding >= 1) ...
    && all(rounding == round(rounding)) && all(suppressBelow >= 0), 'policy');
assert(isscalar(effect) && effect >= 1 && effect <= 10 && effect == round(effect), 'effect');
[O, N] = ndgrid(priorO, ambientN);
W = priorP * ambientP.';
O = O(:);
N = N(:);
W = W(:);
rows0 = outcome_rows(O, max(0, O + N), rounding, suppressBelow);
rows1 = outcome_rows(O, max(0, O + N + effect), rounding, suppressBelow);
[~, ~, idx] = unique([rows0; rows1], 'rows');
n = numel(W);
p0 = accumarray(idx, [W; zeros(n, 1)]);
p1 = accumarray(idx, [zeros(n, 1); W]);
out.advantage = 0.5 * sum(abs(p0 - p1));
out.distinctOutcomes = numel(p0);
end

function rows = outcome_rows(before, after, rounding, suppressBelow)
k = numel(rounding);
rows = zeros(numel(before), 2 * k);
for j = 1:k
    rows(:, 2 * j - 1) = release_value(before, rounding(j), suppressBelow(j));
    rows(:, 2 * j) = release_value(after, rounding(j), suppressBelow(j));
end
end

function v = release_value(x, r, s)
v = floor((2 * x + r) ./ (2 * r)) * r;
v(x < s) = -1;
end
