% SPDX-License-Identifier: MIT OR Apache-2.0
function [n, p, truncationMass] = ambient_pmf_reference(lamIn, lamOut, steps)
%AMBIENT_PMF_REFERENCE Net ambient change: Poisson in minus Poisson out.
%   Rates are per interval; steps intervals are summed. Returns the truncated
%   pmf (positive entries only) and the mass lost to truncation.
%   Not executed in MATLAB or Octave by its author.
if nargin < 3, steps = 1; end
assert(isscalar(lamIn) && isscalar(lamOut) && isfinite(lamIn) && isfinite(lamOut) ...
    && lamIn >= 0 && lamOut >= 0, 'rates');
assert(isscalar(steps) && steps >= 1 && steps <= 1000 && steps == round(steps), 'steps');
muIn = lamIn * steps;
muOut = lamOut * steps;
assert(max(muIn, muOut) <= 500, 'rate too large');
pin = poisson_pmf(muIn, floor(muIn + 12 * sqrt(muIn) + 30));
pout = poisson_pmf(muOut, floor(muOut + 12 * sqrt(muOut) + 30));
p = conv(pin, fliplr(pout));
n = (0:numel(p) - 1).' - (numel(pout) - 1);
p = p(:);
keep = p > 0;
n = n(keep);
p = p(keep);
truncationMass = max(0, 1 - sum(p));
end

function p = poisson_pmf(mu, kmax)
k = 0:kmax;
if mu == 0
    p = zeros(1, kmax + 1);
    p(1) = 1;
else
    p = exp(-mu + k * log(mu) - gammaln(k + 1));
end
end
