**Source:** Mathiopoulos, Ohnishi & Feher, IEE Proc. I, vol. 136, no. 2, 1989. DOI: [10.1049/ip-i-2.1989.0024](https://doi.org/10.1049/ip-i-2.1989.0024)

## Normalization

Given $N$ measured points $(f_i, y_i)$ over bandwidth $B$ centered at $f_0$:

$$x_i = \frac{f_i - f_0}{B/2}, \quad x_i \in [-1, 1]$$

## Legendre Fit

Expand:

$$y(x) = \sum_{n=0}^{K} c_n \, P_n(x)$$

$P_n$ are Legendre polynomials, orthogonal on $[-1, 1]$:

$$\int_{-1}^{1} P_m(x)\, P_n(x)\, dx = \frac{2}{2n+1}\, \delta_{mn}$$

First four:

$$P_0(x) = 1, \quad P_1(x) = x, \quad P_2(x) = \frac{1}{2}(3x^2 - 1), \quad P_3(x) = \frac{1}{2}(5x^3 - 3x)$$

Coefficients $c_n$ via least-squares (`numpy.polynomial.legendre.legfit`).

In the continuous orthogonal basis (or when discrete sampling/weighting makes the basis orthogonal under the discrete inner product), $c_n$ are independent of fit order $K$: adding higher terms does not change lower coefficients. In practice, with discrete least-squares fitting, this property holds approximately, though lower-order coefficients may shift slightly when $K$ changes.

## Peak-to-Peak Distortion

$$\Delta y_n = \max_{x \in [-1,1]} \bigl[ c_n\, P_n(x) \bigr] - \min_{x \in [-1,1]} \bigl[ c_n\, P_n(x) \bigr]$$

| Component       | $P_n$ range over $[-1,1]$ | $\Delta y_n$                   |
| --------------- | ------------------------- | ------------------------------ |
| Constant $n=0$  | $[1,\; 1]$                | $0$                            |
| Linear $n=1$    | $[-1,\; 1]$               | $2\lvert c_1 \rvert$           |
| Parabolic $n=2$ | $[-\frac{1}{2},\; 1]$     | $\frac{3}{2}\lvert c_2 \rvert$ |
| Cubic $n=3$     | $[-1,\; 1]$               | $2\lvert c_3 \rvert$           |

Parabolic derivation: $P_2(\pm 1) = 1$, $P_2(0) = -\frac{1}{2}$, range $= 1 - (-\frac{1}{2}) = \frac{3}{2}$.

## Visualization on Original Plot

Overlay individual $c_n\, P_n(x)$ components (offset by $c_0$) on the measurement. Annotate $\Delta y_n$ as vertical double-arrows:

- **Linear** $\Delta y_1$: vertical distance between band edges ($x = -1$ to $x = +1$).
- **Parabolic** $\Delta y_2$: vertical distance between band center ($x = 0$) and band edge ($x = \pm 1$). Sign of $c_2$ determines which is the max: $c_2 > 0$ gives min at center, max at edges; $c_2 < 0$ the opposite.
- **Cubic** $\Delta y_3$: edge-to-edge like linear ($\lvert P_3(\pm 1)\rvert = 1$ are the global extrema).

## Interpretation by Quantity

| Quantity         | $c_0$   | $c_1$                  | $c_2$          | $c_3$          |
| ---------------- | ------- | ---------------------- | -------------- | -------------- |
| Amplitude [dB]   | Nominal | **Distortion**         | **Distortion** | **Distortion** |
| Phase [rad]      | Offset  | **Ideal** (pure delay) | **Distortion** | **Distortion** |
| Group delay [ns] | Nominal | **Distortion**         | **Distortion** | **Distortion** |

For phase, $c_1$ encodes constant group delay $\tau_0 = -c_1 / (\pi B)$. First phase distortion term is $c_2$.

Derivative relationship: For $\phi(f) = \sum c_n P_n(x)$ with $x$ the normalized frequency, $\tau_g(f) = -\frac{1}{2\pi}\frac{d\phi}{df} = -\frac{1}{2\pi}\frac{dx}{df}\sum c_n P_n'(x)$. Each $P_n'(x)$ expands as a linear combination of lower-order Legendre polynomials, so a single phase coefficient $c_n$ contributes to multiple group-delay coefficients. For example, $P_3'(x) = 5P_2(x) + P_0(x)$. The bandwidth scaling factor $dx/df$ (the normalization constant used to convert $f \to x$) must be included to compute the mixed coefficients correctly.

## Physical Unit Conversion

$$\text{slope} = \frac{c_1}{B/2} \quad \left[\frac{\text{unit}}{\text{Hz}}\right]$$

$$\text{curvature} = \frac{3\, c_2}{(B/2)^2} \quad \left[\frac{\text{unit}}{\text{Hz}^2}\right]$$

## Practical Distortion Values

Final reported values are in vertical units only (dB, ns, rad, ...). Normalizing to $[-1, 1]$ before fitting absorbs bandwidth into $c_n$:

$$\boxed{\Delta y_{\text{linear}} = 2\,\lvert c_1 \rvert}$$

$$\boxed{\Delta y_{\text{parabolic}} = \frac{3}{2}\,\lvert c_2 \rvert}$$