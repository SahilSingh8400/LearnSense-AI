/**
 * LearnSense AI - PDF Report Generator
 * Generates high-resolution, vector-based PDF summary reports directly in the browser
 * with zero external dependencies, 100% offline-ready, standard PDF 1.4 compliant.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.LearnSensePDF = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {

  class LearnSensePDFGenerator {
    constructor() {
      this.pageWidth = 595.28; // A4 pt (8.27 in)
      this.pageHeight = 841.89; // A4 pt (11.69 in)
      this.marginLeft = 36;
      this.marginRight = 36;
      this.marginTop = 36;
      this.marginBottom = 44;
      this.contentWidth = this.pageWidth - this.marginLeft - this.marginRight;
      
      this.pages = [];
      this.currentPageIndex = -1;
      this.cursorY = this.marginTop;
      this.addNewPage();
    }

    addNewPage() {
      this.currentPageIndex++;
      this.pages.push({ stream: [] });
      this.cursorY = this.marginTop + 16;
    }

    get currentStream() {
      return this.pages[this.currentPageIndex].stream;
    }

    toPdfY(yFromTop) {
      return this.pageHeight - yFromTop;
    }

    checkPageBreak(neededHeight) {
      if (this.cursorY + neededHeight > this.pageHeight - this.marginBottom) {
        this.addNewPage();
        return true;
      }
      return false;
    }

    drawRect(x, y, w, h, fillRgb = null, strokeRgb = null, lineWidth = 1) {
      const pdfY = this.toPdfY(y + h);
      let cmd = 'q\n';
      if (lineWidth) cmd += `${lineWidth.toFixed(2)} w\n`;
      if (strokeRgb) cmd += `${strokeRgb[0].toFixed(3)} ${strokeRgb[1].toFixed(3)} ${strokeRgb[2].toFixed(3)} RG\n`;
      if (fillRgb) cmd += `${fillRgb[0].toFixed(3)} ${fillRgb[1].toFixed(3)} ${fillRgb[2].toFixed(3)} rg\n`;
      cmd += `${x.toFixed(2)} ${pdfY.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re\n`;
      if (fillRgb && strokeRgb) cmd += 'B\n';
      else if (fillRgb) cmd += 'f\n';
      else if (strokeRgb) cmd += 'S\n';
      cmd += 'Q\n';
      this.currentStream.push(cmd);
    }

    drawLine(x1, y1, x2, y2, strokeRgb = [0.85, 0.88, 0.92], lineWidth = 0.5) {
      const pdfY1 = this.toPdfY(y1);
      const pdfY2 = this.toPdfY(y2);
      let cmd = `q\n${lineWidth.toFixed(2)} w\n${strokeRgb[0].toFixed(3)} ${strokeRgb[1].toFixed(3)} ${strokeRgb[2].toFixed(3)} RG\n`;
      cmd += `${x1.toFixed(2)} ${pdfY1.toFixed(2)} m ${x2.toFixed(2)} ${pdfY2.toFixed(2)} l S\nQ\n`;
      this.currentStream.push(cmd);
    }

    escapeText(str) {
      if (str == null) return '';
      return String(str)
        .replace(/\\/g, '\\\\')
        .replace(/\(/g, '\\(')
        .replace(/\)/g, '\\)')
        .replace(/[^\x20-\x7E\xA0-\xFF]/g, ' '); // Clean to WinAnsi printable chars
    }

    drawText(text, x, y, options = {}) {
      const size = options.size || 10;
      const font = options.font || 'F1'; // F1: Helvetica, F2: Helvetica-Bold, F3: Helvetica-Oblique
      const color = options.color || [0.1, 0.1, 0.15];
      const pdfY = this.toPdfY(y);

      const safeText = this.escapeText(text);
      let cmd = 'BT\n';
      cmd += `/${font} ${size.toFixed(2)} Tf\n`;
      cmd += `${color[0].toFixed(3)} ${color[1].toFixed(3)} ${color[2].toFixed(3)} rg\n`;
      cmd += `${x.toFixed(2)} ${pdfY.toFixed(2)} Td\n`;
      cmd += `(${safeText}) Tj\n`;
      cmd += 'ET\n';
      this.currentStream.push(cmd);
    }

    measureTextWidth(text, size, font = 'F1') {
      const factor = (font === 'F2') ? 0.56 : 0.51;
      return String(text || '').length * size * factor;
    }

    wrapText(text, maxWidth, fontSize, font = 'F1') {
      if (!text) return [];
      const factor = (font === 'F2') ? 0.56 : 0.51;
      const avgCharWidth = fontSize * factor;
      const maxChars = Math.max(8, Math.floor(maxWidth / avgCharWidth));
      const words = String(text).split(/\s+/);
      const lines = [];
      let currentLine = '';

      for (const word of words) {
        if (!currentLine) {
          currentLine = word;
        } else if ((currentLine + ' ' + word).length <= maxChars) {
          currentLine += ' ' + word;
        } else {
          lines.push(currentLine);
          currentLine = word;
        }
      }
      if (currentLine) lines.push(currentLine);
      return lines;
    }

    drawHeaderBanner(userData, overallData) {
      const bannerH = 74;
      const bgRgb = [0.06, 0.09, 0.16];
      const borderRgb = [0.16, 0.22, 0.35];

      this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, bannerH, bgRgb, borderRgb, 1);
      this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, 3, [0.49, 0.42, 0.99], null, 0);

      this.drawText('LearnSense AI', this.marginLeft + 16, this.cursorY + 25, {
        font: 'F2',
        size: 18,
        color: [1, 1, 1]
      });

      this.drawText('DSA Learning Analytics & Performance Summary Report', this.marginLeft + 16, this.cursorY + 41, {
        font: 'F1',
        size: 9.5,
        color: [0.65, 0.72, 0.85]
      });

      const rightX = this.marginLeft + this.contentWidth - 16;
      const userEmail = (userData && (userData.email || userData.name)) || 'DSA Learner';
      const reportDate = new Date().toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });

      const emailStr = `Learner: ${userEmail}`;
      this.drawText(emailStr, rightX - this.measureTextWidth(emailStr, 9, 'F2'), this.cursorY + 23, {
        font: 'F2',
        size: 9,
        color: [0.9, 0.93, 0.98]
      });

      const dateStr = `Generated: ${reportDate}`;
      this.drawText(dateStr, rightX - this.measureTextWidth(dateStr, 8.5, 'F1'), this.cursorY + 38, {
        font: 'F1',
        size: 8.5,
        color: [0.65, 0.72, 0.85]
      });

      const scoreVal = overallData ? overallData.overall_skill_score : null;
      let tier = overallData && overallData.skill_level;
      if (!tier && scoreVal != null) {
        if (scoreVal >= 85) tier = 'Expert';
        else if (scoreVal >= 70) tier = 'Proficient';
        else if (scoreVal >= 55) tier = 'Developing';
        else if (scoreVal >= 35) tier = 'Beginner';
        else tier = 'Novice';
      }

      const tierStr = scoreVal != null
        ? `Skill Tier: ${tier || 'Proficient'} (${scoreVal}/100)`
        : 'Skill Tier: In Evaluation';

      this.drawText(tierStr, rightX - this.measureTextWidth(tierStr, 8.5, 'F2'), this.cursorY + 53, {
        font: 'F2',
        size: 8.5,
        color: [0.55, 0.85, 0.65]
      });

      this.cursorY += bannerH + 14;
    }

    drawHeroStats(overallData) {
      const o = overallData || {};
      const cardGap = 8;
      const numCards = 4;
      const cardW = (this.contentWidth - (cardGap * (numCards - 1))) / numCards;
      const cardH = 48;

      const scoreVal = o.overall_skill_score != null ? `${o.overall_skill_score}/100` : '—';
      const tierText = o.skill_level || (o.overall_skill_score >= 70 ? 'Proficient' : 'In Practice');

      const cards = [
        {
          title: 'DSA SKILL SCORE',
          value: scoreVal,
          sub: `${tierText} Tier`,
          valColor: [0.43, 0.36, 0.98]
        },
        {
          title: 'PROBLEMS SOLVED',
          value: String(o.solved_problems || 0),
          sub: `${o.correct || 0} correct / ${o.wrong || 0} wrong`,
          valColor: [0.08, 0.58, 0.35]
        },
        {
          title: 'OVERALL ACCURACY',
          value: `${o.accuracy || 0}%`,
          sub: 'Attempt Success Rate',
          valColor: [0.12, 0.45, 0.85]
        },
        {
          title: 'DAY STREAK',
          value: `${o.streak_days || 0} Days`,
          sub: 'Consistent Practice',
          valColor: [0.85, 0.45, 0.08]
        }
      ];

      cards.forEach((c, idx) => {
        const cardX = this.marginLeft + idx * (cardW + cardGap);
        this.drawRect(cardX, this.cursorY, cardW, cardH, [0.97, 0.98, 1.0], [0.88, 0.90, 0.95], 0.8);
        this.drawRect(cardX, this.cursorY, cardW, 2, c.valColor, null, 0);

        this.drawText(c.title, cardX + 8, this.cursorY + 13, {
          font: 'F2',
          size: 7.2,
          color: [0.4, 0.45, 0.55]
        });

        this.drawText(c.value, cardX + 8, this.cursorY + 28, {
          font: 'F2',
          size: 13,
          color: c.valColor
        });

        this.drawText(c.sub, cardX + 8, this.cursorY + 40, {
          font: 'F1',
          size: 6.8,
          color: [0.5, 0.55, 0.65]
        });
      });

      this.cursorY += cardH + 16;
    }

    drawSectionHeading(title, subtitle = null) {
      this.checkPageBreak(38);
      this.drawRect(this.marginLeft, this.cursorY, 4, 14, [0.43, 0.36, 0.98], null, 0);

      this.drawText(title, this.marginLeft + 10, this.cursorY + 11, {
        font: 'F2',
        size: 10.5,
        color: [0.1, 0.14, 0.22]
      });

      if (subtitle) {
        const offset = this.marginLeft + 10 + this.measureTextWidth(title, 10.5, 'F2') + 8;
        this.drawText(subtitle, offset, this.cursorY + 11, {
          font: 'F1',
          size: 8,
          color: [0.5, 0.55, 0.65]
        });
      }

      this.cursorY += 18;
    }

    drawAIReportSection(reportData, overallData) {
      // If reportData is missing or empty, synthesize an algorithmic summary from overallData
      let report = reportData;
      if (!report || (!report.skill_summary && !report.strengths && !report.recommendations)) {
        const solved = (overallData && overallData.solved_problems) || 0;
        const acc = (overallData && overallData.accuracy) || 0;
        const streak = (overallData && overallData.streak_days) || 0;
        report = {
          skill_summary: `Algorithmic analysis based on ${solved} solved DSA problems with an overall accuracy of ${acc}% and an active streak of ${streak} days. Practice shows active mastery across core problem types with steady analytical pacing.`,
          strengths: [
            `Demonstrated resilience with ${solved} completed DSA challenges`,
            `Consistent practice cadence with a ${streak}-day active practice momentum`,
            `Solid accuracy rate of ${acc}% across recorded problem attempts`
          ],
          weaknesses: [
            'Continue optimizing space bounds in multi-branch recursion',
            'Reinforce edge-case validation on extreme numerical inputs'
          ],
          recommendations: [
            {
              priority: 'HIGH',
              topic: 'Dynamic Programming & Memoization',
              reason: 'Focus on transitioning recursion tree subproblems into optimal space tabulation.'
            },
            {
              priority: 'MEDIUM',
              topic: 'Trees & Graph Traversals',
              reason: 'Solidify BFS queue and DFS backtracking state transitions.'
            }
          ],
          learning_path: [
            'Review foundational two-pointer and sliding window window invariants',
            'Master top 15 recursive tree questions with iterative and recursive approaches',
            'Benchmark space/time trade-offs across hash structures vs binary search'
          ],
          weekly_target: `Solve 5 medium-difficulty problems focusing on optimal time complexity bounds.`,
          encouragement: 'Great dedication to continuous algorithmic improvement! Keep up the daily practice discipline.'
        };
      }

      this.drawSectionHeading('AI Performance Assessment & Learning Report', 'Personalized synthesis');

      // 1. Skill Summary Box
      if (report.skill_summary) {
        const lines = this.wrapText(report.skill_summary, this.contentWidth - 24, 8.5, 'F1');
        const boxH = Math.max(34, lines.length * 12 + 20);

        this.checkPageBreak(boxH + 8);
        this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, boxH, [0.96, 0.96, 0.99], [0.82, 0.82, 0.95], 0.8);
        this.drawRect(this.marginLeft, this.cursorY, 3, boxH, [0.43, 0.36, 0.98], null, 0);

        this.drawText('EXECUTIVE SUMMARY & ALGORITHMIC PROFILE', this.marginLeft + 12, this.cursorY + 12, {
          font: 'F2',
          size: 7.5,
          color: [0.35, 0.3, 0.75]
        });

        let textY = this.cursorY + 24;
        lines.forEach((line) => {
          this.drawText(line, this.marginLeft + 12, textY, {
            font: 'F1',
            size: 8.5,
            color: [0.15, 0.2, 0.28]
          });
          textY += 12;
        });

        this.cursorY += boxH + 12;
      }

      // 2. Strengths and Weaknesses Side-by-Side
      const strengths = report.strengths || [];
      const weaknesses = report.weaknesses || [];

      if (strengths.length || weaknesses.length) {
        const colGap = 10;
        const colW = (this.contentWidth - colGap) / 2;

        const sLines = [];
        strengths.forEach((s) => {
          const wrapped = this.wrapText(`+ ${s}`, colW - 16, 8, 'F1');
          sLines.push(...wrapped);
        });

        const wLines = [];
        weaknesses.forEach((w) => {
          const wrapped = this.wrapText(`! ${w}`, colW - 16, 8, 'F1');
          wLines.push(...wrapped);
        });

        const maxLines = Math.max(sLines.length, wLines.length, 2);
        const cardH = maxLines * 12 + 26;

        this.checkPageBreak(cardH + 8);

        // Left Column: Strengths
        const leftX = this.marginLeft;
        this.drawRect(leftX, this.cursorY, colW, cardH, [0.96, 0.99, 0.97], [0.8, 0.9, 0.82], 0.8);
        this.drawRect(leftX, this.cursorY, colW, 2, [0.08, 0.6, 0.35], null, 0);
        this.drawText('KEY STRENGTHS IDENTIFIED', leftX + 10, this.cursorY + 14, {
          font: 'F2',
          size: 7.5,
          color: [0.08, 0.5, 0.28]
        });

        let sy = this.cursorY + 26;
        sLines.forEach((l) => {
          this.drawText(l, leftX + 10, sy, {
            font: 'F1',
            size: 8,
            color: [0.15, 0.25, 0.18]
          });
          sy += 12;
        });

        // Right Column: Weaknesses / Growth Areas
        const rightX = this.marginLeft + colW + colGap;
        this.drawRect(rightX, this.cursorY, colW, cardH, [1.0, 0.98, 0.95], [0.95, 0.88, 0.78], 0.8);
        this.drawRect(rightX, this.cursorY, colW, 2, [0.85, 0.45, 0.08], null, 0);
        this.drawText('AREAS FOR GROWTH & GAPS', rightX + 10, this.cursorY + 14, {
          font: 'F2',
          size: 7.5,
          color: [0.75, 0.38, 0.05]
        });

        let wy = this.cursorY + 26;
        wLines.forEach((l) => {
          this.drawText(l, rightX + 10, wy, {
            font: 'F1',
            size: 8,
            color: [0.3, 0.2, 0.1]
          });
          wy += 12;
        });

        this.cursorY += cardH + 12;
      }

      // 3. Recommended Priorities
      const recs = report.recommendations || [];
      if (recs.length) {
        this.checkPageBreak(50);
        this.drawText('RECOMMENDED PRACTICE PRIORITIES', this.marginLeft, this.cursorY + 8, {
          font: 'F2',
          size: 8,
          color: [0.3, 0.35, 0.45]
        });
        this.cursorY += 14;

        recs.forEach((rec) => {
          const priority = (rec.priority || 'HIGH').toUpperCase();
          const pColor = priority === 'HIGH' ? [0.85, 0.2, 0.2] : priority === 'MEDIUM' ? [0.85, 0.55, 0.08] : [0.15, 0.6, 0.3];
          const topic = rec.topic || 'DSA Topic';
          const reason = rec.reason || '';
          const lines = this.wrapText(reason, this.contentWidth - 180, 8, 'F1');
          const itemH = Math.max(22, lines.length * 11 + 10);

          this.checkPageBreak(itemH + 4);
          this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, itemH, [0.98, 0.98, 1.0], [0.90, 0.92, 0.96], 0.6);

          this.drawRect(this.marginLeft + 8, this.cursorY + 5, 48, 12, null, pColor, 0.7);
          this.drawText(priority, this.marginLeft + 16, this.cursorY + 14, {
            font: 'F2',
            size: 7,
            color: pColor
          });

          this.drawText(topic, this.marginLeft + 64, this.cursorY + 14, {
            font: 'F2',
            size: 8.5,
            color: [0.1, 0.15, 0.25]
          });

          let ry = this.cursorY + 14;
          lines.forEach((l) => {
            this.drawText(l, this.marginLeft + 175, ry, {
              font: 'F1',
              size: 8,
              color: [0.35, 0.4, 0.5]
            });
            ry += 11;
          });

          this.cursorY += itemH + 4;
        });

        this.cursorY += 8;
      }

      // 4. Learning Path & Coach Advice
      const pathSteps = report.learning_path || [];
      const target = report.weekly_target;
      const encouragement = report.encouragement;

      if (pathSteps.length || target || encouragement) {
        const colGap = 10;
        const colW = (this.contentWidth - colGap) / 2;

        let leftH = 26 + pathSteps.length * 16;
        let rightH = 26 + (target ? 32 : 0) + (encouragement ? 36 : 0);
        const secH = Math.max(leftH, rightH, 44);

        this.checkPageBreak(secH + 8);

        if (pathSteps.length) {
          const lx = this.marginLeft;
          this.drawRect(lx, this.cursorY, colW, secH, [0.98, 0.98, 1.0], [0.88, 0.9, 0.96], 0.8);
          this.drawText('SUGGESTED LEARNING PATH', lx + 10, this.cursorY + 14, {
            font: 'F2',
            size: 7.5,
            color: [0.35, 0.3, 0.75]
          });

          let py = this.cursorY + 26;
          pathSteps.forEach((step, sIdx) => {
            const sLines = this.wrapText(`${sIdx + 1}. ${step}`, colW - 18, 7.8, 'F1');
            sLines.forEach((sl) => {
              this.drawText(sl, lx + 10, py, {
                font: 'F1',
                size: 7.8,
                color: [0.2, 0.25, 0.35]
              });
              py += 11;
            });
            py += 2;
          });
        }

        if (target || encouragement) {
          const rx = this.marginLeft + colW + colGap;
          this.drawRect(rx, this.cursorY, colW, secH, [0.97, 0.99, 1.0], [0.85, 0.9, 0.96], 0.8);
          this.drawText('WEEKLY TARGET & COACH ADVICE', rx + 10, this.cursorY + 14, {
            font: 'F2',
            size: 7.5,
            color: [0.1, 0.45, 0.7]
          });

          let cy = this.cursorY + 28;
          if (target) {
            this.drawText('Target:', rx + 10, cy, { font: 'F2', size: 8, color: [0.1, 0.15, 0.25] });
            const tLines = this.wrapText(target, colW - 48, 7.8, 'F1');
            tLines.forEach((tl) => {
              this.drawText(tl, rx + 44, cy, { font: 'F1', size: 7.8, color: [0.25, 0.3, 0.4] });
              cy += 11;
            });
            cy += 4;
          }

          if (encouragement) {
            this.drawText('Coach:', rx + 10, cy, { font: 'F2', size: 8, color: [0.1, 0.5, 0.3] });
            const eLines = this.wrapText(encouragement, colW - 48, 7.8, 'F3');
            eLines.forEach((el) => {
              this.drawText(el, rx + 44, cy, { font: 'F3', size: 7.8, color: [0.25, 0.3, 0.4] });
              cy += 11;
            });
          }
        }

        this.cursorY += secH + 16;
      }
    }

    drawSkillsTable(topics) {
      if (!topics || !topics.length) return;

      this.checkPageBreak(60);
      this.drawSectionHeading('DSA Topic Skill Proficiency Map', `${topics.length} topics evaluated`);

      const colWidths = [150, 70, 95, 95, 105];
      const headers = ['Topic', 'Skill Score', 'Proficiency Tier', 'Confidence', 'Problems Analyzed'];
      const rowH = 18;

      const renderHeader = () => {
        this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, rowH, [0.12, 0.16, 0.25], null, 0);
        let x = this.marginLeft;
        headers.forEach((h, idx) => {
          this.drawText(h, x + 8, this.cursorY + 12, {
            font: 'F2',
            size: 7.5,
            color: [0.95, 0.96, 1.0]
          });
          x += colWidths[idx];
        });
        this.cursorY += rowH;
      };

      renderHeader();

      topics.forEach((t, rIdx) => {
        if (this.checkPageBreak(rowH + 2)) {
          renderHeader();
        }

        const bgRgb = rIdx % 2 === 0 ? [0.99, 0.99, 1.0] : [0.95, 0.96, 0.98];
        this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, rowH, bgRgb, [0.88, 0.9, 0.94], 0.5);

        let rx = this.marginLeft;
        this.drawText(t.topic || 'General DSA', rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 8,
          color: [0.1, 0.15, 0.25]
        });
        rx += colWidths[0];

        const scoreStr = `${t.score || 0} / 100`;
        this.drawText(scoreStr, rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 8,
          color: (t.score >= 75) ? [0.08, 0.55, 0.3] : (t.score >= 50) ? [0.2, 0.45, 0.8] : [0.8, 0.4, 0.05]
        });
        rx += colWidths[1];

        this.drawText(t.label || 'Developing', rx + 8, this.cursorY + 12, {
          font: 'F1',
          size: 8,
          color: [0.3, 0.35, 0.45]
        });
        rx += colWidths[2];

        const confStr = `${Math.round((t.confidence || 0.8) * 100)}% Confidence`;
        this.drawText(confStr, rx + 8, this.cursorY + 12, {
          font: 'F1',
          size: 7.8,
          color: [0.4, 0.45, 0.55]
        });
        rx += colWidths[3];

        const seenStr = `${t.problems_seen || 1} problem${(t.problems_seen || 1) > 1 ? 's' : ''}`;
        this.drawText(seenStr, rx + 8, this.cursorY + 12, {
          font: 'F1',
          size: 7.8,
          color: [0.4, 0.45, 0.55]
        });

        this.cursorY += rowH;
      });

      this.cursorY += 16;
    }

    drawProblemsTable(problems) {
      if (!problems || !problems.length) return;

      this.checkPageBreak(60);
      this.drawSectionHeading('Problem Performance & Algorithmic Complexity Log', `${problems.length} problems attempted`);

      const colWidths = [145, 55, 55, 55, 105, 100];
      const headers = ['Problem Title', 'Correct', 'Wrong', 'Accuracy', 'Complexity & Optimality', 'Last Solved'];
      const rowH = 18;

      const renderHeader = () => {
        this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, rowH, [0.12, 0.16, 0.25], null, 0);
        let x = this.marginLeft;
        headers.forEach((h, idx) => {
          this.drawText(h, x + 8, this.cursorY + 12, {
            font: 'F2',
            size: 7.5,
            color: [0.95, 0.96, 1.0]
          });
          x += colWidths[idx];
        });
        this.cursorY += rowH;
      };

      renderHeader();

      problems.forEach((p, rIdx) => {
        if (this.checkPageBreak(rowH + 2)) {
          renderHeader();
        }

        const bgRgb = rIdx % 2 === 0 ? [0.99, 0.99, 1.0] : [0.95, 0.96, 0.98];
        this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, rowH, bgRgb, [0.88, 0.9, 0.94], 0.5);

        let rx = this.marginLeft;
        const titleStr = p.title && p.title.length > 25 ? p.title.substring(0, 24) + '...' : (p.title || 'Problem');
        this.drawText(titleStr, rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 7.8,
          color: [0.1, 0.15, 0.25]
        });
        rx += colWidths[0];

        this.drawText(String(p.correct || 0), rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 8,
          color: [0.08, 0.58, 0.32]
        });
        rx += colWidths[1];

        this.drawText(String(p.wrong || 0), rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 8,
          color: (p.wrong > 0) ? [0.85, 0.2, 0.2] : [0.5, 0.55, 0.6]
        });
        rx += colWidths[2];

        this.drawText(`${p.accuracy || 0}%`, rx + 8, this.cursorY + 12, {
          font: 'F1',
          size: 8,
          color: [0.15, 0.2, 0.3]
        });
        rx += colWidths[3];

        const isOpt = p.is_optimal !== false;
        const tc = p.time_complexity || 'O(n)';
        const compLabel = `${tc} · ${isOpt ? 'Optimal' : 'Suboptimal'}`;
        this.drawText(compLabel, rx + 8, this.cursorY + 12, {
          font: 'F2',
          size: 7.5,
          color: isOpt ? [0.08, 0.55, 0.3] : [0.85, 0.45, 0.05]
        });
        rx += colWidths[4];

        const dateStr = p.last_solved_at ? new Date(p.last_solved_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
        this.drawText(dateStr, rx + 8, this.cursorY + 12, {
          font: 'F1',
          size: 7.5,
          color: [0.45, 0.5, 0.6]
        });

        this.cursorY += rowH;
      });

      this.cursorY += 16;
    }

    drawLearningGoals(goalData) {
      if (!goalData || !goalData.goal) return;
      const g = goalData.goal;

      this.checkPageBreak(45);
      this.drawSectionHeading('Personal Learning Goals & Target Commitments');

      const boxH = 34;
      this.drawRect(this.marginLeft, this.cursorY, this.contentWidth, boxH, [0.97, 0.98, 1.0], [0.86, 0.90, 0.96], 0.8);

      const typeStr = g.type === 'placement' ? 'Campus Placement / FAANG' : g.type === 'exam' ? 'College / Competitive Exam' : 'General DSA Practice';
      this.drawText(`Target Track: ${typeStr}`, this.marginLeft + 12, this.cursorY + 14, {
        font: 'F2',
        size: 8,
        color: [0.15, 0.2, 0.3]
      });

      const targetStr = `Daily Commitment: ${g.daily_target_minutes || 60} mins/day`;
      this.drawText(targetStr, this.marginLeft + 220, this.cursorY + 14, {
        font: 'F1',
        size: 8,
        color: [0.35, 0.4, 0.5]
      });

      if (g.target_date) {
        this.drawText(`Target Deadline: ${g.target_date}`, this.marginLeft + 380, this.cursorY + 14, {
          font: 'F1',
          size: 8,
          color: [0.35, 0.4, 0.5]
        });
      }

      if (g.notes) {
        this.drawText(`Note: ${g.notes}`, this.marginLeft + 12, this.cursorY + 26, {
          font: 'F3',
          size: 7.5,
          color: [0.45, 0.5, 0.6]
        });
      }

      this.cursorY += boxH + 16;
    }

    buildPDFString() {
      const totalPages = this.pages.length;
      for (let i = 0; i < totalPages; i++) {
        const pageNum = i + 1;
        const stream = this.pages[i].stream;
        
        const pdfFooterLineY = 28;
        let footerCmd = `q\n0.5 w\n0.82 0.85 0.90 RG\n${this.marginLeft} ${pdfFooterLineY} m ${(this.pageWidth - this.marginRight)} ${pdfFooterLineY} l S\nQ\n`;
        footerCmd += `BT\n/F1 7.5 Tf\n0.5 0.55 0.65 rg\n${this.marginLeft} 16 Td\n(Generated by LearnSense AI - Personal DSA Learning & Performance Analytics Platform) Tj\nET\n`;
        footerCmd += `BT\n/F2 7.5 Tf\n0.4 0.45 0.55 rg\n${(this.pageWidth - this.marginRight - 55)} 16 Td\n(Page ${pageNum} of ${totalPages}) Tj\nET\n`;
        stream.push(footerCmd);

        if (i > 0) {
          const pdfHeaderLineY = this.pageHeight - 24;
          let headerCmd = `q\n0.5 w\n0.82 0.85 0.90 RG\n${this.marginLeft} ${pdfHeaderLineY} m ${(this.pageWidth - this.marginRight)} ${pdfHeaderLineY} l S\nQ\n`;
          headerCmd += `BT\n/F2 7.5 Tf\n0.35 0.4 0.5 rg\n${this.marginLeft} ${(this.pageHeight - 18)} Td\n(LearnSense AI - DSA Performance & Analytics Summary Report) Tj\nET\n`;
          headerCmd += `BT\n/F1 7.5 Tf\n0.5 0.55 0.65 rg\n${(this.pageWidth - this.marginRight - 110)} ${(this.pageHeight - 18)} Td\n(Confidential Performance Data) Tj\nET\n`;
          stream.unshift(headerCmd);
        }
      }

      // Calculate byte lengths safely in browser and node
      function getByteLength(str) {
        if (typeof Buffer !== 'undefined') return Buffer.byteLength(str, 'utf8');
        return new TextEncoder().encode(str).length;
      }

      const offsets = [];
      let out = '%PDF-1.4\n%\xE2\xE3\xCF\xD3\n';

      function addRawObject(objId, content) {
        offsets[objId] = getByteLength(out);
        out += `${objId} 0 obj\n${content}\nendobj\n`;
      }

      addRawObject(1, '<< /Type /Catalog /Pages 2 0 R >>');

      const pageObjIds = [];
      for (let i = 0; i < totalPages; i++) {
        pageObjIds.push(7 + 2 * i);
      }
      const kidsStr = pageObjIds.map(id => `${id} 0 R`).join(' ');

      addRawObject(2, `<< /Type /Pages /Kids [ ${kidsStr} ] /Count ${totalPages} >>`);
      addRawObject(3, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
      addRawObject(4, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
      addRawObject(5, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>');

      for (let i = 0; i < totalPages; i++) {
        const streamObjId = 6 + 2 * i;
        const pageObjId = 7 + 2 * i;
        const streamContent = this.pages[i].stream.join('\n');
        const streamLength = getByteLength(streamContent);

        addRawObject(streamObjId, `<< /Length ${streamLength} >>\nstream\n${streamContent}\nendstream`);
        addRawObject(pageObjId, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${this.pageWidth} ${this.pageHeight}] /Contents ${streamObjId} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> >>`);
      }

      const totalObjs = 5 + 2 * totalPages;
      const xrefOffset = getByteLength(out);

      out += `xref\n0 ${totalObjs + 1}\n`;
      out += `0000000000 65535 f \n`;
      for (let i = 1; i <= totalObjs; i++) {
        out += String(offsets[i]).padStart(10, '0') + ' 00000 n \n';
      }

      out += `trailer\n<< /Size ${totalObjs + 1} /Root 1 0 R >>\n`;
      out += `startxref\n${xrefOffset}\n%%EOF\n`;

      return out;
    }

    buildPDFBlob() {
      const pdfStr = this.buildPDFString();
      if (typeof TextEncoder !== 'undefined') {
        const uint8 = new TextEncoder().encode(pdfStr);
        return new Blob([uint8], { type: 'application/pdf' });
      }
      return new Blob([pdfStr], { type: 'application/pdf' });
    }

    download(filename = 'LearnSense_AI_Report.pdf') {
      const blob = this.buildPDFBlob();
      if (typeof window !== 'undefined' && window.document) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 1500);
      }
    }
  }

  /**
   * One-tap helper to assemble report data and trigger PDF download.
   */
  function generateAndDownloadReport(data, customFilename) {
    const generator = new LearnSensePDFGenerator();

    const userData = data.user || {};
    const overallData = (data.overall) || (data.fullData && data.fullData.overall) || {};
    const reportData = (data.report) || (data.reportData && data.reportData.report) || null;
    const topics = data.topics || (data.fullData && data.fullData.topics) || [];
    const problems = data.problems || (data.fullData && data.fullData.problems) || [];
    const goals = data.goals || null;

    generator.drawHeaderBanner(userData, overallData);
    generator.drawHeroStats(overallData);
    generator.drawAIReportSection(reportData, overallData);
    generator.drawSkillsTable(topics);
    generator.drawProblemsTable(problems);
    generator.drawLearningGoals(goals);

    const safeName = (userData.email || userData.name || 'Learner').split('@')[0].replace(/[^a-zA-Z0-9_-]/g, '_');
    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = customFilename || `LearnSense_Report_${safeName}_${dateStr}.pdf`;

    generator.download(filename);
    return generator;
  }

  return {
    LearnSensePDFGenerator,
    generateAndDownloadReport
  };
});
