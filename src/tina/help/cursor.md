Places two frequency markers on the trace and reports the measured value at each, along with their difference.

## Delta Calculation

Given values $v_1$ and $v_2$ read at Cursor 1 ($f_1$) and Cursor 2 ($f_2$):

$$\Delta = v_2 - v_1$$

The sign reflects direction: positive if $v_2 > v_1$, negative otherwise.

Result is in the same unit as the trace (dB for magnitude, degrees or radians for phase).

## Value Reading

Each cursor value is linearly interpolated between the two nearest measured frequency points. Let $f_a$, $f_b$ be the bounding points with values $v_a$, $v_b$:

$$v = v_a + (v_b - v_a) \cdot \frac{f - f_a}{f_b - f_a}$$

For background on subtraction, see [Wikipedia: Subtraction](https://en.wikipedia.org/wiki/Subtraction).
