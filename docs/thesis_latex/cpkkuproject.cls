% ===============================
% cpkkuproject.cls
% Thai Project / Report Class (XeLaTeX)
% College of Computing style (5 chapters)
% ===============================
% https://github.com/sekz-zz/kkuthesis/blob/master/kkuthesis.cls

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{cpkkuproject}

\newcommand{\ThaiAlph}[1]{%
  \ifcase#1\relax ก\or ข\or ค\or ง\or จ\or ฉ\or ช\or ซ\or ฌ\or ญ\or ฎ\or ฏ\or ฐ\or ฑ\or ฒ\or ณ\or ด\or ต\or ถ\or ท\or ธ\or น\or บ\or ป\or ผ\or ฝ\or พ\or ฟ\or ภ\or ม\or ย\or ร\or ล\or ว\or ศ\or ษ\or ส\or ห\or ฬ\or อ\or ฮ\else ?\fi
}


% ------------------------------------------------
% Base class
% ------------------------------------------------
\LoadClass[12pt,oneside]{report}
% ------------------------------------------------
% Paragraph indentation
% ------------------------------------------------
\RequirePackage{indentfirst}

\newlength{\firstindentlength}
\newlength{\secondindentlength}
\newlength{\thirdindentlength}

\setlength{\firstindentlength}{3em}
\setlength{\secondindentlength}{7.1em}
\setlength{\thirdindentlength}{12.2em}

\setlength{\parindent}{\firstindentlength}
\setlength{\parskip}{0pt}
% ------------------------------------------------
% Require XeLaTeX
% ------------------------------------------------
\RequirePackage{ifxetex}
\ifxetex\else
  \ClassError{cpkkuproject}
    {This class requires XeLaTeX}
    {Please compile using XeLaTeX}
\fi

% ------------------------------------------------
% Page layout
% ------------------------------------------------
\RequirePackage[a4paper,margin=1in]{geometry}

% ------------------------------------------------
% Packages
% ------------------------------------------------
\RequirePackage{amsmath,amssymb}
\RequirePackage{newtxmath}
\RequirePackage{fontspec}
\RequirePackage{setspace}
\RequirePackage{graphicx}
\RequirePackage{booktabs}
\RequirePackage{caption}
\RequirePackage{subcaption}
\RequirePackage{float}
\RequirePackage{fancyhdr}
\RequirePackage{titlesec}
\RequirePackage{microtype}
\RequirePackage{xurl}
\RequirePackage{enumitem}
\RequirePackage{etoolbox}
\RequirePackage{listings}


\setlist[itemize]{%
  label=\textbullet
}
\setlist[enumerate]{label*=\arabic*.}

\setlist[itemize,1]{%
  leftmargin=*,
  labelindent=\parindent,
  labelsep=1em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.3\baselineskip,
  partopsep=0pt,
}
\setlist[itemize,2]{%
  leftmargin=*,
  labelindent=0em,
  labelsep=1em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.3\baselineskip,
  partopsep=0pt,
}
\setlist[itemize,3]{%
  leftmargin=*,
  labelindent=0em,
  labelsep=1em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.3\baselineskip,
  partopsep=0pt,
}

\setlist[enumerate,1]{%
  label=\thesection.\arabic*.,
  leftmargin=*,
  labelwidth=3.5em,
  labelindent=\parindent,
  labelsep=1em,
  listparindent=0pt,
}
\setlist[enumerate,2]{%
  label=\thesection.\arabic{enumi}.\arabic*.,
  leftmargin=*,
  labelwidth=4.5em,
  labelindent=0em,
  labelsep=1em,
  listparindent=0pt
}
\setlist[enumerate,3]{%
  label=\thesection.\arabic{enumi}.\arabic{enumii}.\arabic*.,
  leftmargin=*,
  labelwidth=5.5em,
  labelindent=0em,
  labelsep=1em,
  listparindent=0pt
}

\setlist[description]{%
  leftmargin=*,
  labelindent=\parindent,
  labelsep=1em,
  listparindent=0pt,
}


\RequirePackage[
  colorlinks=true,
  linkcolor=black,
  urlcolor=blue,
  pageanchor=false
]{hyperref}

\RequirePackage{caption}
\captionsetup[table]{labelfont=bf,labelsep=space}
\captionsetup[figure]{labelfont=bf,labelsep=space}

\makeatletter
\newcommand{\IfEmptyTF}[3]{%
  \edef\@temp{#1}%
  \ifx\@temp\@empty
    #2% true (empty)
  \else
    #3% false (not empty)
  \fi
}
\makeatother
% ------------------------------------------------
% Thai font setup (XeLaTeX)
% ------------------------------------------------
\XeTeXlinebreaklocale "th"
\XeTeXlinebreakskip = 0pt plus 1pt

\pretolerance=1000
\tolerance=2000
\emergencystretch=3em

\setmainfont{Sarabun}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *-Regular,
  BoldFont = *-Bold,
  ItalicFont = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Scale = 1.4,
]

\setsansfont{Sarabun}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *-Regular,
  BoldFont = *-Bold,
  ItalicFont = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Scale = 1.4,
]

\setmonofont{DroidSansMono}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *,
  BoldFont = *,
  ItalicFont = *,
  BoldItalicFont = *,
  Scale = 1.0,
]

% \setmonofont{Courier New}

% ------------------------------------------------
% Equation, Table, Figure Numbering
% ------------------------------------------------
\makeatletter
\@removefromreset{equation}{chapter}
\@removefromreset{figure}{chapter}
\@removefromreset{table}{chapter}
\makeatother

\renewcommand{\theequation}{\arabic{equation}}
\renewcommand{\thefigure}{\arabic{figure}}
\renewcommand{\thetable}{\arabic{table}}

% ------------------------------------------------
% Line spacing
% ------------------------------------------------
\onehalfspacing

% ------------------------------------------------
% Header / Footer
% ------------------------------------------------
\pagestyle{fancy}
\fancyhf{}
% \fancyfoot[R]{\thepage}
\fancyhead[R]{\thepage}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\makeatletter
\let\ps@plain\ps@fancy
\makeatother

% ------------------------------------------------
% Thai names
% ------------------------------------------------
\renewcommand{\contentsname}{สารบัญ}
\renewcommand{\listtablename}{สารบัญตาราง}
\renewcommand{\listfigurename}{สารบัญภาพ}
\renewcommand{\figurename}{ภาพที่}
\renewcommand{\tablename}{ตารางที่}

% ------------------------------------------------
% Centered TOC / LOT / LOF titles (robust)
% ------------------------------------------------
\makeatletter

\renewcommand{\tableofcontents}{
  \chapter*{\centering\Large\bfseries สารบัญ}
  \addcontentsline{toc}{chapter}{สารบัญ}
  \@starttoc{toc}
}


\renewcommand{\listoftables}{
  \chapter*{\centering\Large\bfseries สารบัญตาราง}
  \addcontentsline{toc}{chapter}{สารบัญตาราง}
  \begingroup
    \let\addvspace\@gobble
    \@starttoc{lot}
  \endgroup
}
\renewcommand*\l@table[2]{%
  \@dottedtocline{1}{0em}{1.5em}{ตารางที่~#1}{#2}%
}

\renewcommand{\listoffigures}{
  \chapter*{\centering\Large\bfseries สารบัญภาพ}
  \addcontentsline{toc}{chapter}{สารบัญภาพ}
  \begingroup
    \let\addvspace\@gobble % ตัด vertical space ระหว่าง section/chapter
    \@starttoc{lof}
  \endgroup
}
\renewcommand*\l@figure[2]{%
  \@dottedtocline{1}{0em}{1.5em}{ภาพที่~#1}{#2}%
}

\makeatother


% ------------------------------------------------
% Title Page
% ------------------------------------------------
\makeatletter
\newcommand{\titleTH}[1]{\def\@titleTH{#1}}
\newcommand{\titleEN}[1]{\def\@titleEN{#1}}
\newcommand{\advisorTH}[1]{\def\@advisorTH{#1}}
\newcommand{\advisorEN}[1]{\def\@advisorEN{#1}}
\newcommand{\degreeTH}[1]{\def\@degreeTH{#1}}
\newcommand{\degreeEN}[1]{\def\@degreeEN{#1}}
\newcommand{\majorTH}[1]{\def\@majorTH{#1}}
\newcommand{\majorEN}[1]{\def\@majorEN{#1}}

\newcommand{\printadvisorTH}{\@advisorTH}
\newcommand{\printadvisorEN}{\@advisorEN}

\newcommand{\academicYearEN}[1]{\def\@academicYearEN{#1}}
\newcommand{\academicYearTH}[1]{\def\@academicYearTH{#1}}

\newcommand{\firstStudentID}[1]{\def\@firstStudentID{#1}}
\newcommand{\firstStudentPrefixTH}[1]{\def\@firstStudentPrefixTH{#1}}
\newcommand{\firstStudentNameTH}[1]{\def\@firstStudentNameTH{#1}}
\newcommand{\firstStudentPrefixEN}[1]{\def\@firstStudentPrefixEN{#1}}
\newcommand{\firstStudentNameEN}[1]{\def\@firstStudentNameEN{#1}}

\newcommand{\secondStudentID}[1]{\def\@secondStudentID{#1}}
\newcommand{\secondStudentPrefixTH}[1]{\def\@secondStudentPrefixTH{#1}}
\newcommand{\secondStudentNameTH}[1]{\def\@secondStudentNameTH{#1}}
\newcommand{\secondStudentPrefixEN}[1]{\def\@secondStudentPrefixEN{#1}}
\newcommand{\secondStudentNameEN}[1]{\def\@secondStudentNameEN{#1}}

\newcommand{\maketitlepage}{
\begin{titlepage}
\clearpage
\thispagestyle{empty}
\centering

\includegraphics[scale=0.5]{./theme/kku-logo.png}

{\Large\bfseries เอกสารโครงงานฉบับสมบูรณ์}

\vfill

{\Large \@titleTH \\[0.5cm] \@titleEN}

\vfill

{\large โดย \\}
{\large \@firstStudentID~\@firstStudentPrefixTH\@firstStudentNameTH \\}
{\large \@secondStudentID~\@secondStudentPrefixTH\@secondStudentNameTH \\[2cm]}

{\large อาจารย์ที่ปรึกษา \\ \@advisorTH \\[2cm]}

\vfill

{\large รายงานฉบับนี้เป็นส่วนหนึ่งของการศึกษา\\}
{\large หลักสูตร\@degreeTH{} สาขาวิชา\@majorTH\\}
{\large วิทยาลัยการคอมพิวเตอร์\\}
{\large มหาวิทยาลัยขอนแก่น\\}
{\large ปีการศึกษา \@academicYearTH}

\end{titlepage}
}
\makeatother


% ------------------------------------------------
% Front matter environments
% ------------------------------------------------

\makeatletter
\newenvironment{acknowledgement}{
  \chapter*{กิตติกรรมประกาศ}
  \addcontentsline{toc}{chapter}{กิตติกรรมประกาศ}
}{
\begin{flushright}
ผู้จัดทำ
\\
\@firstStudentNameTH
\\
\IfEmptyTF{\@secondStudentID}{}{\@secondStudentNameTH}
\end{flushright}
\clearpage}
\makeatother

\newenvironment{symbolpage}{
  \chapter*{สัญลักษณ์และคำย่อ}
  \addcontentsline{toc}{chapter}{สัญลักษณ์และคำย่อ}
}{\clearpage}

% ------------------------------------------------
% Five-Chapter Structure (Thai standard)
% ------------------------------------------------
\newcommand{\chapterone}{\chapter{บทนำ}\input{chapter1}}
\newcommand{\chaptertwo}{\chapter{เอกสารและงานวิจัยที่เกี่ยวข้อง}\input{chapter2}}
\newcommand{\chapterthree}{\chapter{วิธีดำเนินการวิจัย}\input{chapter3}}
\newcommand{\chapterfour}{\chapter{ผลการทดลองและอภิปรายผล}\input{chapter4}}
\newcommand{\chapterfive}{\chapter{สรุปผลและข้อเสนอแนะ}\input{chapter5}}

% ------------------------------------------------
% Bibliography (Thai)
% ------------------------------------------------
\renewcommand{\bibname}{บรรณานุกรม}


% ------------------------------------------------
% Appendices
% ------------------------------------------------

\newcommand{\appendiceschapter}[1]{%
  \clearpage
  \thispagestyle{empty}
  \vspace*{\fill}%
  
  \refstepcounter{chapter}%
  
  \begin{center}
    \if\relax\detokenize{#1}\relax
      {\Large\bfseries ภาคผนวก}%
    \else
      {\Large\bfseries ภาคผนวก~\ThaiAlph{\value{chapter}}}%
      \\
      {\Large\bfseries #1}
    \fi
  \end{center}
  
  \vspace{\fill}        
  \clearpage
  
  % TOC
  \if\relax\detokenize{#1}\relax
    \addcontentsline{toc}{chapter}{ภาคผนวก}%
  \else
    \addcontentsline{toc}{chapter}{ภาคผนวก~\ThaiAlph{\value{chapter}}: #1}%
  \fi

  \ifnum\value{chapter}=0
    \appendix
  \fi
}

% ------------------------------------------------
% Chapter title format (Thai standard)
% ------------------------------------------------
\titleformat{\chapter}[display]
  {\bfseries\Large\centering}
  {บทที่~\thechapter}
  {1ex}
  {}

\titleformat{name=\chapter,numberless}[block]
  {\bfseries\Large\centering}
  {}
  {0pt}{}

\titlespacing*{\chapter}
  {0pt}
  {0pt}
  {20pt}

\setcounter{secnumdepth}{3}
\renewcommand\thesection{\thechapter.\arabic{section}}
\renewcommand\thesubsection{\thesection.\arabic{subsection}}
\renewcommand\thesubsubsection{\thesubsection.\arabic{subsubsection}}

\titleformat{\section}
  {\bfseries\large\upshape}
  {\thesection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\section,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

\titleformat{\subsection}
  {\bfseries\large\upshape}
  {\thesubsection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\subsection,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

\titleformat{\subsubsection}
  {\bfseries\large\upshape}
  {\thesubsubsection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\subsubsection,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

\titlespacing{\section}
  {0pt}
  {0.5\baselineskip}
  {0.0\baselineskip}

\titlespacing{\subsection}
  {\firstindentlength}
  {0.5\baselineskip}
  {0.0\baselineskip}

\titlespacing{\subsubsection}
  {\secondindentlength}
  {0.5\baselineskip}
  {0.0\baselineskip}

\pretocmd{\section}{\setlength{\parindent}{\firstindentlength}}{}{}
\pretocmd{\subsection}{\setlength{\parindent}{\secondindentlength}}{}{}
\pretocmd{\subsubsection}{\setlength{\parindent}{\thirdindentlength}}{}{}


\makeatletter

\newif\if@appendixmode
\@appendixmodefalse

\pretocmd{\appendix}{%
  \@appendixmodetrue
}{}{}


\pretocmd{\section}{%
  \if@appendixmode\else
    \setlength{\parindent}{\firstindentlength}%
  \fi
}{}{}

\pretocmd{\subsection}{%
  \if@appendixmode\else
    \setlength{\parindent}{\secondindentlength}%
  \fi
}{}{}

\pretocmd{\subsubsection}{%
  \if@appendixmode\else
    \setlength{\parindent}{\thirdindentlength}%
  \fi
}{}{}

\makeatother

% ------------------------------------------------
% Abstract
% ------------------------------------------------

\newcommand{\projectentry}[2]{%
\parindent=0pt
\hangindent=0pt
\hangafter=1
  {\parindent=0pt
   \hangindent=\firstindentlength
   \hangafter=1
   #1\par}
#2\par
}


\makeatletter

\newcommand{\@keywordsTH}{}
\newcommand{\@keywordsEN}{}

\newcommand{\keywordsTH}[1]{%
  \gdef\@keywordsTH{#1}%
}
\newcommand{\keywordsEN}[1]{%
  \gdef\@keywordsEN{#1}%
}
\newcommand{\printkeywordsTH}{%
  \par\bigskip
  \noindent\textbf{คำสำคัญ: } \@keywordsTH
}
\newcommand{\printkeywordsEN}{%
  \par\bigskip
  \noindent\textbf{Keywords: } \@keywordsEN
}

\newenvironment{abstractTH}{%
  \clearpage
  \addcontentsline{toc}{chapter}{บทคัดย่อ}

  \projectentry
  {
  \IfEmptyTF{\@secondStudentID}
      {\@firstStudentNameTH.}
      {\@firstStudentNameTH\ และ \@secondStudentNameTH.}
  \@academicYearTH{}. \textbf{\@titleTH{}.}
   โครงงานคอมพิวเตอร์. ปริญญา\@degreeTH{} หลักสูตร\@majorTH{} สาขาวิชาวิทยาการคอมพิวเตอร์
   วิทยาลัยการคอมพิวเตอร์ มหาวิทยาลัยขอนแก่น.}
  {\textbf{อาจารย์ที่ปรึกษา:} \@advisorTH}

  \vspace{2.5mm}
  \begin{center}\large\textbf{บทคัดย่อ}\end{center}
  \vspace{2.5mm}
  
  \setlength{\parindent}{\firstindentlength}
  \@afterindenttrue
}{\printkeywordsTH\clearpage}

\newenvironment{abstractEN}{%
  \clearpage
  \addcontentsline{toc}{chapter}{ABSTRACT}

  \projectentry
  {
  \IfEmptyTF{\@secondStudentID}
      {\@firstStudentNameEN.}
      {\@firstStudentNameEN\ and \@secondStudentNameEN.}
  \@academicYearEN{}. \textbf{\@titleEN{}.}
   Computer Project, \@degreeEN{}, Program in \@majorEN{}, Department of Computer Science, College of Computing, Khon Kaen University.}
  {\textbf{Project Advisor:} \@advisorEN}

  \vspace{2.5mm}
  \begin{center}\large\textbf{ABSTRACT}\end{center}
  \vspace{2.5mm}
  
  \setlength{\parindent}{\firstindentlength}
  \@afterindenttrue
}{\printkeywordsEN\clearpage}

\makeatother

% ------------------------------------------------
% End of class
% ------------------------------------------------